"""Own the bundled Rust service; spawned workers inherit its private endpoint."""

from __future__ import annotations

import atexit
import json
import os
from pathlib import Path
import queue
import secrets
import subprocess
import sys
import threading
from typing import Callable

from jesse.services.coordination_client import Client, CoordinationConnectionError


# This is inherited process configuration, never a project file or CLI argument.
RUNTIME_ENV = 'JESSE_COORDINATION_RUNTIME'
# Python/NumPy imports on a cold Windows installation need more than an RPC timeout.
STARTUP_TIMEOUT = 20
_lock = threading.RLock()
_process: subprocess.Popen | None = None
_settings: dict | None = None
_stopping = False
_started_once = False
_failed = False
_log_thread: threading.Thread | None = None


class ManagedClient(Client):
    """Defer connection until CLI bootstrap, without starting services on import."""

    def __init__(self) -> None:
        super().__init__('127.0.0.1', 0, secrets.token_hex(32), 'pending')
        self._configured = False

    def connect(self) -> str:
        with _lock:
            if _process is None or _settings is None:
                raise CoordinationConnectionError('Start Jesse with jesse run before using shared state')
            if _process.poll() is not None:
                raise CoordinationConnectionError('The bundled coordinator stopped; restart the Jesse instance')
            if not self._configured:
                self.address = ('127.0.0.1', _settings['port'])
                self.token = _settings['token']
                self.namespace = _settings['namespace']
                self.generation = _settings['generation']
                self._configured = True
        return super().connect()


def create_client(env_values: dict, *, owner: bool = False) -> Client:
    """Use the owner's inherited endpoint, explicit external settings, or managed mode."""
    if owner:
        # A nested CLI owns a new instance; only spawned workers adopt a parent endpoint.
        os.environ.pop(RUNTIME_ENV, None)
        os.environ.pop('JESSE_COORDINATION_GENERATION', None)
    inherited = os.environ.get(RUNTIME_ENV)
    if inherited:
        settings = json.loads(inherited)
        return Client('127.0.0.1', settings['port'], settings['token'], settings['namespace'],
                      generation=settings['generation'])
    # Explicit settings remain available for isolated tests and existing service deployments.
    if env_values.get('COORDINATION_TOKEN') or env_values.get('COORDINATION_NAMESPACE'):
        return Client(
            host=env_values.get('COORDINATION_HOST', '127.0.0.1'),
            port=int(env_values.get('COORDINATION_PORT', '6381')),
            token=env_values.get('COORDINATION_TOKEN', ''),
            namespace=env_values.get('COORDINATION_NAMESPACE', ''),
            generation=os.environ.get('JESSE_COORDINATION_GENERATION'),
        )
    return ManagedClient()


def _drain(stream, log: Path) -> None:
    """Keep Rust diagnostics drained even if the local log becomes unwritable."""
    try:
        for line in stream:
            try:
                # Bound the log to the latest diagnostics rather than filling a user's disk.
                if log.exists() and log.stat().st_size > 1024 * 1024:
                    log.replace(log.with_suffix('.previous.log'))
                fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                with os.fdopen(fd, 'w', encoding='utf-8') as output:
                    output.write(line)
            except OSError:
                pass
    finally:
        stream.close()


def start(client: Client) -> None:
    """Bind an OS-assigned loopback port and authenticate before accepting any work."""
    global _process, _settings, _stopping, _started_once, _failed, _log_thread
    if not isinstance(client, ManagedClient):
        os.environ['JESSE_COORDINATION_GENERATION'] = client.connect()
        return
    with _lock:
        if _process is not None:
            client.connect()
            return
        if _started_once:
            raise CoordinationConnectionError('Restart Jesse to create a fresh coordinator generation')
        _started_once = True
        _stopping = False
        _failed = False
        token = secrets.token_hex(32)
        namespace = secrets.token_hex(16)
        env = {**os.environ, 'JESSE_COORDINATION_TOKEN': token,
               'JESSE_COORDINATION_BIND': '127.0.0.1:0', 'JESSE_COORDINATION_PARENT_PIPE': '1'}
        log = Path('storage/logs/coordinator.log').resolve()
        log.parent.mkdir(parents=True, exist_ok=True)
        # Loading the installed extension uses the same version/platform build as indicators.
        # Stdin is a private ownership pipe; Rust exits when this process dies or closes it.
        process = subprocess.Popen(
            [sys.executable, '-u', '-c', 'import jesse_rust; jesse_rust.run_coordinator()'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, text=True, encoding='utf-8', errors='replace', start_new_session=os.name != 'nt',
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )
        _process = process
        assert process.stdout is not None and process.stderr is not None
        _log_thread = threading.Thread(target=_drain, args=(process.stderr, log), daemon=True)
        _log_thread.start()
        lines: queue.Queue[str] = queue.Queue(maxsize=1)
        threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
        try:
            line = lines.get(timeout=STARTUP_TIMEOUT).strip()
            prefix = 'jesse-coordinator listening on 127.0.0.1:'
            if not line.startswith(prefix):
                raise CoordinationConnectionError(f'Bundled coordinator failed to start; see {log}')
            port = int(line[len(prefix):])
            probe = Client('127.0.0.1', port, token, namespace)
            try:
                generation = probe.connect()
            finally:
                probe.close()
            _settings = {'port': port, 'token': token, 'namespace': namespace, 'generation': generation}
            os.environ[RUNTIME_ENV] = json.dumps(_settings)
            os.environ['JESSE_COORDINATION_GENERATION'] = generation
            client.connect()
        except queue.Empty:
            stop()
            raise CoordinationConnectionError(f'Bundled coordinator startup timed out; see {log}') from None
        except BaseException:
            stop()
            raise


def monitor(on_failure: Callable[[], None]) -> None:
    """Request application shutdown after child death; never restart empty shared state."""
    process = _process
    if process is None:
        return

    def watch() -> None:
        global _failed
        process.wait()
        if not _stopping:
            _failed = True
            sys.stderr.write('Jesse coordinator stopped unexpectedly. Stopping Jesse; restart it to continue.\n')
            on_failure()

    threading.Thread(target=watch, daemon=True).start()


def failed() -> bool:
    """Expose child failure so supervisors receive a nonzero application exit."""
    return _failed


def stop() -> None:
    """Stop only this process's owned service, after its jobs have been drained."""
    global _process, _settings, _stopping, _log_thread
    with _lock:
        process = _process
        if process is None:
            return
        _stopping = True
        if process.stdin is not None:
            process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        if _log_thread is not None:
            # The exited child closes stderr; finish writing its startup/failure diagnostics.
            _log_thread.join(timeout=2)
            _log_thread = None
        if process.stdout is not None:
            process.stdout.close()
        _process = None
        _settings = None
        os.environ.pop(RUNTIME_ENV, None)
        os.environ.pop('JESSE_COORDINATION_GENERATION', None)


atexit.register(stop)
