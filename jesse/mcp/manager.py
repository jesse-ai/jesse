"""
MCP Worker Lifecycle Management

`jesse run` starts the MCP server as a separate worker process (jesse.mcp.server) that
listens on loopback only. MCP clients never connect to it directly: they use the
authenticated /mcp route on the dashboard origin, which relays each request to the worker
on the port recorded here.

The worker's port is chosen by the OS and handed over without a race:
1. This process binds a TCP socket to 127.0.0.1:0 and starts listening, so the kernel
   assigns a port no other socket holds, and the port is owned from that moment on.
2. The listening socket itself, not just its port number, is handed to the worker: on
   POSIX the worker inherits that one descriptor; on Windows it receives socket.share()
   data on its stdin.
3. The /mcp route forwards only while the worker owning that socket is alive.

The port is never closed and bound again in between, so no other process can take it,
and concurrent Jesse instances on one machine always get different ports.

USAGE:
------
Called from CLI (cli.py) when Jesse starts: run_mcp_server(host, port, dashboard_url)
Called on shutdown: terminate_mcp_server()
"""

import os
import signal
import socket
import subprocess
import sys
from dataclasses import dataclass
from typing import IO, Any, Dict, List, Mapping, Optional, Tuple, Union

import click

import jesse.helpers as jh
import jesse.mcp.mcp_config as mcp_config
from jesse.services.dashboard_url import internal_api_url, mcp_endpoint_url

# Matches uvicorn's default backlog, which the worker's server applies to the socket again
# when it starts serving. Until then, early connections wait in this queue.
_LISTEN_BACKLOG = 2048

# How long run_mcp_server watches a new worker for an immediate exit before reporting it
# as running. Jesse's startup does not wait for the worker to finish loading (that takes
# seconds): requests arriving earlier wait in the socket's backlog. Later failures are
# caught by running_worker_port(), which the /mcp route checks on every request.
_STARTUP_CHECK_SECONDS = 0.2

# Grace period for the worker to shut down after SIGTERM before it is killed.
_STOP_TIMEOUT_SECONDS = 5

# Where a worker's stdout/stderr go: None inherits this process's, or a file/descriptor.
_Output = Union[None, int, IO[Any]]


@dataclass
class McpWorker:
    """A started MCP worker process and the internal loopback port its socket owns."""

    process: subprocess.Popen
    port: int
    # Windows only: this process's handle to the shared listening socket, kept until the
    # worker stops (see start_worker). Always None on POSIX.
    held_socket: Optional[socket.socket] = None

    def is_running(self) -> bool:
        return self.process.poll() is None

    def release_socket(self) -> None:
        """Close this process's handle to the listening socket, if it still holds one."""
        if self.held_socket is not None:
            self.held_socket.close()
            self.held_socket = None

    def stop(self, timeout: float = _STOP_TIMEOUT_SECONDS) -> None:
        """Terminate the worker, kill it if it outlives `timeout`, and release the socket."""
        try:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    _kill(self.process)
        finally:
            self.release_socket()


# The worker started by `jesse run` in this process, or None when none is running.
MCP_WORKER: Optional[McpWorker] = None


def _signal_handler(signum, frame):
    """Handle termination signals to gracefully shut down the MCP server."""
    signal_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
    print(f"\n🛑 Received {signal_name}, shutting down MCP server...")

    # Terminate MCP server
    terminate_mcp_server()

    print("👋 MCP server shutdown complete")
    sys.exit(0)


def _kill(process: subprocess.Popen) -> None:
    """Kill a worker and reap it, tolerating one that has already exited."""
    try:
        process.kill()
    except OSError:
        pass
    try:
        process.wait(timeout=_STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        pass


def reserve_worker_socket() -> socket.socket:
    """
    Return a listening TCP socket on the loopback worker host with an OS-assigned port.

    The socket is non-inheritable (PEP 446): only a worker it is explicitly handed to
    receives it, never an unrelated child process.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            # Windows lets another socket of the same user that sets SO_REUSEADDR bind a
            # port that is already in use. Exclusive use rules that out; POSIX never allows
            # it without SO_REUSEPORT on both sockets, which is not set here.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind((mcp_config.MCP_WORKER_HOST, 0))
        sock.listen(_LISTEN_BACKLOG)
    except BaseException:
        sock.close()
        raise
    return sock


def build_worker_launch(
    api_url: str,
    dashboard_url: str,
    password: str,
    listen_fd: Optional[int],
    base_env: Optional[Mapping[str, str]] = None,
) -> Tuple[List[str], Dict[str, str]]:
    """
    Return the argv and environment used to start the MCP worker process.

    `listen_fd` is the descriptor number of the listening socket the worker inherits
    (POSIX). None means the worker reads socket.share() data from its stdin (Windows).
    The password travels in the child's environment rather than argv, because command
    lines are readable by every user on the machine. `api_url` is the internal API
    address and `dashboard_url` the public origin.
    """
    argv = [
        sys.executable, "-m",
        "jesse.mcp.server",
        "--api_url", api_url,
        "--dashboard_url", dashboard_url,
    ]
    if listen_fd is None:
        argv.append("--listen_share")
    else:
        argv += ["--listen_fd", str(listen_fd)]
    env = dict(os.environ if base_env is None else base_env)
    env[mcp_config.WORKER_PASSWORD_ENV] = password
    return argv, env


def start_worker(
    api_url: str,
    dashboard_url: str,
    password: str,
    stdout: _Output = None,
    stderr: _Output = None,
    cwd: Optional[str] = None,
    base_env: Optional[Mapping[str, str]] = None,
) -> McpWorker:
    """
    Reserve a loopback port and start a worker process that serves on it.

    On any failure, including cancellation, the reserved socket is closed and a worker
    that was already spawned is killed, so nothing is left holding the port.
    """
    sock = reserve_worker_socket()
    port = sock.getsockname()[1]
    process: Optional[subprocess.Popen] = None
    try:
        if sys.platform == 'win32':
            argv, env = build_worker_launch(api_url, dashboard_url, password, None, base_env)
            process = subprocess.Popen(
                argv, env=env, cwd=cwd, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, shell=False,
            )
            assert process.stdin is not None
            # share() duplicates the socket for this worker's process ID only. Windows may
            # close the underlying socket if the source handle closes before the worker
            # has attached to it, so this handle is kept until the worker stops. No fork
            # exists there, so holding it cannot leak it into other processes.
            process.stdin.write(sock.share(process.pid))
            process.stdin.close()
            return McpWorker(process, port, held_socket=sock)

        argv, env = build_worker_launch(api_url, dashboard_url, password, sock.fileno(), base_env)
        # pass_fds makes exactly this descriptor inheritable in the child, under the same
        # number; close_fds (the default) closes every other descriptor there.
        process = subprocess.Popen(
            argv, env=env, cwd=cwd, pass_fds=(sock.fileno(),), stdout=stdout, stderr=stderr, shell=False,
        )
    except BaseException:
        if process is not None:
            _kill(process)
        sock.close()
        raise

    # Popen returns only after the child has exec'd, so the worker now holds its own
    # descriptor for the socket. Closing this copy means the port is released as soon as
    # the worker exits, and processes this one forks later (such as fork-started
    # multiprocessing workers) never inherit the listener.
    sock.close()
    return McpWorker(process, port)


def _forget_worker(worker: McpWorker) -> None:
    """Drop `worker` as the published worker (if it is) and release its socket handle."""
    global MCP_WORKER
    if MCP_WORKER is worker:
        MCP_WORKER = None
        mcp_config.MCP_WORKER_PORT = None
    worker.release_socket()


def running_worker_port() -> Optional[int]:
    """
    Return the internal port of the running worker, or None when no worker is running.

    A worker that has exited is forgotten here, so its port, which the OS may hand to
    another process, is never used again.
    """
    worker = MCP_WORKER
    if worker is None:
        return None
    if not worker.is_running():
        _forget_worker(worker)
        return None
    return worker.port


def is_worker_running() -> bool:
    return running_worker_port() is not None


def _wait_for_early_exit(process: subprocess.Popen) -> Optional[int]:
    """Return the worker's exit code if it exits within the startup check, else None."""
    try:
        return process.wait(timeout=_STARTUP_CHECK_SECONDS)
    except subprocess.TimeoutExpired:
        return None


def _notice_legacy_port_setting(env_values: Mapping[str, Any]) -> None:
    """Tell users with an old MCP_PORT in .env that it is ignored and can be removed."""
    raw = env_values.get(mcp_config.LEGACY_PORT_ENV_KEY)
    if raw is None or not str(raw).strip():
        return
    print(jh.color(
        f"{mcp_config.LEGACY_PORT_ENV_KEY} in your .env file is no longer used and can be removed: "
        "Jesse picks a free internal port for the MCP worker automatically.",
        'yellow',
    ))


def run_mcp_server(jesse_host: str, jesse_port: int, dashboard_url: str) -> None:
    """
    Start the Jesse MCP worker as a subprocess on an OS-assigned loopback port.

    Clients connect through the authenticated /mcp route on the dashboard origin; the
    internal port is only recorded for that route and never shown as an endpoint.

    Args:
        jesse_host: Bind address of the Jesse API (e.g., "0.0.0.0")
        jesse_port: Port number for the Jesse API (e.g., 9000)
        dashboard_url: Validated public dashboard origin (DASHBOARD_URL or its default)

    Raises:
        Exception: If the server fails to start or exits immediately
    """
    global MCP_WORKER

    if is_worker_running():
        print(jh.color("MCP Server is already running", "yellow"))
        return

    from jesse.services.env import ENV_VALUES

    # Tools reach the API directly on this machine, never through the public URL.
    mcp_config.JESSE_API_URL = internal_api_url(jesse_host, jesse_port)
    mcp_config.DASHBOARD_URL = dashboard_url
    mcp_config.MCP_URL = mcp_endpoint_url(dashboard_url)

    # The worker authenticates MCP clients and calls the API with the dashboard password.
    password = ENV_VALUES.get('PASSWORD') or ''
    if not password:
        raise Exception("PASSWORD not found in .env file. Required for MCP authentication.")

    _notice_legacy_port_setting(ENV_VALUES)

    # Read the MCP_LOG_IN_TERMINAL from the .env file, if not set, use the default value (True)
    show_logs_in_terminal = (ENV_VALUES.get('MCP_LOG_IN_TERMINAL') or 'true').strip().lower() != 'false'

    worker: Optional[McpWorker] = None
    try:
        with open(os.devnull, 'w') as devnull:
            # None keeps MCP output/errors visible in the terminal.
            output = None if show_logs_in_terminal else devnull
            worker = start_worker(
                mcp_config.JESSE_API_URL, dashboard_url, password, stdout=output, stderr=output,
            )

        exit_code = _wait_for_early_exit(worker.process)
        if exit_code is not None:
            raise Exception(f"MCP server exited immediately with code {exit_code}")
    except BaseException as e:
        # Covers Ctrl+C during startup too: nothing may keep running or holding the port.
        if worker is not None:
            worker.stop()
        if isinstance(e, Exception):
            raise Exception(f"Failed to start MCP server: {str(e)}") from e
        raise

    # Publish the worker only once it is known to have started, so the /mcp route never
    # forwards to a port whose worker already failed.
    MCP_WORKER = worker
    mcp_config.MCP_WORKER_PORT = worker.port

    url = mcp_config.MCP_URL
    border = click.style("─" * (len(url) + 32), fg="cyan", bold=True)
    print(click.style("┌" + border + "┐", fg="cyan", bold=True))
    print(
        click.style("│  ", fg="cyan", bold=True)
        + click.style("✓ MCP Server is running at ", fg="white", bold=True)
        + click.style(url, fg="cyan", bold=True)
        + click.style("  │", fg="cyan", bold=True)
    )
    print(click.style("└" + border + "┘", fg="cyan", bold=True))
    print(
        "  MCP clients must send your dashboard token as \"Authorization: Bearer <token>\"."
        " Setup: https://docs.jesse.trade/docs/mcp/setup"
    )
    print()

    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, _signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, _signal_handler)  # Termination signal


def terminate_mcp_server() -> None:
    """
    Stop the Jesse MCP worker gracefully, force-killing it if needed.

    The worker is unpublished first, so the /mcp route stops forwarding to its port
    before the port is released.
    """
    worker = MCP_WORKER
    if worker is None:
        return
    _forget_worker(worker)
    try:
        print(jh.color("Stopping MCP Server...", 'yellow'))
        worker.stop()
        print(jh.color("✓ MCP Server stopped", 'green'))
    except Exception as e:
        print(jh.color(f"⚠ Error stopping MCP: {str(e)}", 'yellow'))
        _kill(worker.process)
    finally:
        worker.release_socket()
        print(jh.color("✓ MCP Server terminated", 'green'))
