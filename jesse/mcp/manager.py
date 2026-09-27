"""
MCP Server Lifecycle Management

This module manages the MCP server process lifecycle:
- Starts the MCP server as a subprocess with proper configuration
- Monitors server startup and handles errors
- Provides graceful shutdown functionality

The MCP server runs in a separate process, allowing it to operate independently
from the main Jesse application while sharing the same Python environment.

USAGE:
------
Called from CLI (cli.py) when Jesse starts: run_mcp_server(host, port, dashboard_url)
Called on shutdown: terminate_mcp_server()
"""

import sys
import os
import signal
from typing import Dict, List, Mapping, Optional, Tuple
import click
import jesse.helpers as jh
import jesse.mcp.mcp_config as mcp_config
from jesse.services.dashboard_url import internal_api_url, mcp_endpoint_url


# Global variable to store the MCP process handle
MCP_PROCESS = None


def _signal_handler(signum, frame):
    """Handle termination signals to gracefully shut down the MCP server."""
    signal_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
    print(f"\n🛑 Received {signal_name}, shutting down MCP server...")

    # Terminate MCP server
    terminate_mcp_server()

    print("👋 MCP server shutdown complete")
    sys.exit(0)

def build_worker_launch(
    api_url: str,
    dashboard_url: str,
    port: int,
    password: str,
    base_env: Optional[Mapping[str, str]] = None,
) -> Tuple[List[str], Dict[str, str]]:
    """
    Return the argv and environment used to start the MCP worker process.

    The password travels in the child's environment rather than argv, because command
    lines are readable by every user on the machine. The worker binds to loopback on
    `port`; `api_url` is the internal API address and `dashboard_url` the public origin.
    """
    argv = [
        sys.executable, "-m",
        "jesse.mcp.server",
        "--port", str(port),
        "--api_url", api_url,
        "--dashboard_url", dashboard_url,
    ]
    env = dict(os.environ if base_env is None else base_env)
    env[mcp_config.WORKER_PASSWORD_ENV] = password
    return argv, env


def run_mcp_server(jesse_host: str, jesse_port: int, dashboard_url: str) -> None:
    """
    Start the Jesse MCP Server as a subprocess.

    Reads MCP_PORT from .env file or uses default (9002) for the loopback-only worker.
    Clients connect through the authenticated /mcp route on the dashboard origin.

    Args:
        jesse_host: Bind address of the Jesse API (e.g., "0.0.0.0")
        jesse_port: Port number for the Jesse API (e.g., 9000)
        dashboard_url: Validated public dashboard origin (DASHBOARD_URL or its default)

    Raises:
        Exception: If the server fails to start or exits immediately
    """
    global MCP_PROCESS
    
    # Check if the MCP server is already running
    if MCP_PROCESS and MCP_PROCESS.poll() is None:
        print(jh.color("MCP Server is already running", "yellow"))
        return

    from jesse.services.env import ENV_VALUES

    # Tools reach the API directly on this machine, never through the public URL.
    mcp_config.JESSE_API_URL = internal_api_url(jesse_host, jesse_port)
    mcp_config.MCP_PORT = mcp_config.configured_worker_port(ENV_VALUES)
    mcp_config.DASHBOARD_URL = dashboard_url
    mcp_config.MCP_URL = mcp_endpoint_url(dashboard_url)

    # The worker authenticates MCP clients and calls the API with the dashboard password.
    password = ENV_VALUES.get('PASSWORD') or ''
    if not password:
        raise Exception("PASSWORD not found in .env file. Required for MCP authentication.")

    # Read the MCP_LOG_IN_TERMINAL from the .env file, if not set, use the default value (True)
    show_logs_in_terminal = (ENV_VALUES.get('MCP_LOG_IN_TERMINAL') or 'true').strip().lower() != 'false'

    argv, env = build_worker_launch(
        mcp_config.JESSE_API_URL, dashboard_url, mcp_config.MCP_PORT, password,
    )

    # Start the MCP server in a separate process and return the process handle
    try:
        import subprocess
        with open(os.devnull, 'w') as devnull:
            process = subprocess.Popen(
                argv,
                env=env,
                # Do not redirect stdout or stderr so MCP output/errors are visible in the terminal
                stdout=devnull if not show_logs_in_terminal else None,
                stderr=devnull if not show_logs_in_terminal else None,
                # Since we are using array arguments, we need to set shell to False
                shell=False  
        )
        # Set the global MCP_PROCESS
        MCP_PROCESS = process
        
        # wait for 0.2 seconds to make sure the process is started
        import time
        time.sleep(0.2)
        if process.poll() is not None:
            out, err = process.communicate()
            print("STDOUT:", out)
            print("STDERR:", err)
            raise Exception(f"MCP server exited immediately with code {process.poll()}")
        
        # If we reach here, the MCP server started successfully
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

    except Exception as e:
        MCP_PROCESS = None
        raise Exception(f"Failed to start MCP server: {str(e)}")
    
def terminate_mcp_server():
    """
    Terminate the Jesse MCP Server process gracefully.
    
    Attempts graceful shutdown (terminate), then force kill if needed.
    Cleans up the global process handle on completion.
    """
    # Stop MCP server if running
    global MCP_PROCESS
    if MCP_PROCESS:
        try:
            print(jh.color("Stopping MCP Server...", 'yellow'))
            MCP_PROCESS.terminate()
            MCP_PROCESS.wait(timeout=5)
            print(jh.color("✓ MCP Server stopped", 'green'))
        except Exception as e:
            print(jh.color(f"⚠ Error stopping MCP: {str(e)}", 'yellow'))
            try:
                print(jh.color("Force killing MCP Server...", 'yellow'))
                MCP_PROCESS.kill()  # Force kill if terminate fails
            except Exception as e:
                print(jh.color(f"⚠ Error force killing MCP: {str(e)}", 'yellow'))
                pass
        finally:
            MCP_PROCESS = None
            print(jh.color("✓ MCP Server terminated", 'green'))
