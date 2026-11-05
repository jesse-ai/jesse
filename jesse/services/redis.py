"""Native shared-state helpers.

The module path and public names remain stable for existing Jesse Live releases.
They use only the Rust coordinator and require no Redis client packages.
"""

import simplejson as json
import time
import jesse.helpers as jh
from jesse.libs.custom_json import NpEncoder
import os
import base64
import errno
from jesse.services.env import ENV_VALUES
from jesse.services import session_liveness
from jesse.services.coordination_runtime import create_client
from jesse.services.coordination_client import (
    Client, AsyncClient, CoordinationConnectionError, CoordinationBusyError, CoordinationError, CoordinationCapacityError, CoordinationSizeError, LockError as NativeLockError,
)

# Keep the public helper names used by released Jesse Live plugins. All clients
# and exception aliases below belong to the native coordinator.
BACKEND = 'rust'
# Redis selectors from older projects are ignored; managed startup replaces that service.
if ENV_VALUES.get('COORDINATION_BACKEND', os.environ.get('COORDINATION_BACKEND', 'rust')) not in ('rust', 'redis'):
    raise ValueError('Only the Rust coordinator is supported')
RedisConnectionError = CoordinationConnectionError
RedisTimeoutError = TimeoutError
LockError = NativeLockError

async_redis = None
sync_redis = None
_last_active_check_error_at = 0
_active_check_failures_since = 0.0
_active_check_failures = 0
if jh.is_jesse_project() and not jh.is_notebook():
    # Importing CLI commands must not require a running service. Bootstrap connects
    # before work starts and exports a pinned endpoint for all spawned processes.
    sync_redis = create_client(ENV_VALUES)
    async_redis = AsyncClient(sync_redis)


def sync_publish(event: str, msg, compression: bool = False):
    if jh.is_unit_testing():
        raise EnvironmentError('sync_publish() should be NOT called during testing. There must be something wrong')

    # Anything a research worker publishes is a sign of life; progress events also carry how far it got.
    session_liveness.beat(
        msg.get('current') if event.endswith('progressbar') and isinstance(msg, dict) else None
    )

    if compression:
        msg = jh.gzip_compress(msg)
        # Encode the compressed message using Base64
        msg = base64.b64encode(msg).decode('utf-8')

    try:
        sync_redis.publish(
            f"{ENV_VALUES['APP_PORT']}:channel:1", json.dumps({
                'id': os.getpid(),
                'event': f'{jh.app_mode()}.{event}',
                'is_compressed': compression,
                'data': msg
            }, ignore_nan=True, cls=NpEncoder)
        )
    except Exception as e:
        if isinstance(e, (CoordinationCapacityError, CoordinationSizeError)):
            # A rejected/oversized result must fail visibly instead of marking a
            # session successful while silently withholding its dashboard data.
            raise
        # Log publish errors so we can diagnose coordinator outages without crashing the worker
        jh.terminal_debug(f"Coordinator publish error: {e}")


async def async_publish(event: str, msg, compression: bool = False):
    if jh.is_unit_testing():
        raise EnvironmentError('sync_publish() should be NOT called during testing. There must be something wrong')

    if compression:
        msg = jh.gzip_compress(msg)
        # Encode the compressed message using Base64
        msg = base64.b64encode(msg).decode('utf-8')

    await async_redis.publish(
        f"{ENV_VALUES['APP_PORT']}:channel:1", json.dumps({
            'id': os.getpid(),
            'event': f'{jh.app_mode()}.{event}',
            'is_compressed': compression,
            'data': msg
        }, ignore_nan=True, cls=NpEncoder)
    )


def live_charts_key(session_id: str) -> str:
    """
    Coordinator key under which a live-trading process stores the full snapshot of
    its strategy-drawn chart data (lines, extra charts, horizontal lines).
    Written by jesse-live's dashboard service; read by the API process to
    hydrate the dashboard chart after a page (re)load.
    """
    return f"{ENV_VALUES['APP_PORT']}|live-charts:{session_id}"


def store_live_charts_snapshot(session_id: str, charts: dict) -> bool:
    """Cache charts for dashboard reloads; allow one week to revisit stopped sessions."""
    try:
        sync_redis.set(
            live_charts_key(session_id),
            json.dumps(charts, ignore_nan=True, cls=NpEncoder),
            ex=60 * 60 * 24 * 7
        )
        return True
    except Exception as e:
        jh.terminal_debug(f'Error storing live charts snapshot in coordinator: {e}')
        return False


def get_live_charts_snapshot(session_id: str) -> dict:
    """Return cached charts, or an empty snapshot when the cache is unavailable."""
    try:
        raw = sync_redis.get(live_charts_key(session_id))
        if raw is None:
            return {}
        return json.loads(raw)
    except Exception as e:
        jh.terminal_debug(f'Error loading live charts snapshot from coordinator: {e}')
        return {}


def is_process_active(client_id: str) -> bool:
    global _last_active_check_error_at, _active_check_failures_since, _active_check_failures

    if jh.is_unit_testing():
        return False

    try:
        is_active = sync_redis.sismember(f"{ENV_VALUES['APP_PORT']}|active-processes", client_id)
        _last_active_check_error_at = 0
        _active_check_failures_since = 0.0
        _active_check_failures = 0
        return is_active
    except CoordinationError as e:
        # A reused port may now belong to another instance. Authentication failure
        # means this worker has lost its service, not that it should adopt the new one.
        if os.environ.get('JESSE_COORDINATION_RUNTIME') and str(e).startswith('auth:'):
            return False
        raise
    except (RedisConnectionError, RedisTimeoutError, OSError) as e:
        now = time.monotonic()
        if os.environ.get('JESSE_COORDINATION_RUNTIME') and not isinstance(e, CoordinationBusyError):
            # An RPC timeout/retired socket is not proof the service died. Probe a
            # fresh connection before cancelling a live worker; do not retry mutations.
            probe = Client(*sync_redis.address, sync_redis.token, sync_redis.namespace)
            try:
                generation = probe.connect()
                if generation != sync_redis.generation:
                    return False
                _active_check_failures_since = 0.0
                _active_check_failures = 0
            except CoordinationError as probe_error:
                if str(probe_error).startswith('auth:'):
                    return False
                raise
            except (CoordinationConnectionError, OSError) as probe_error:
                cause = probe_error.__cause__ or probe_error
                if isinstance(cause, ConnectionRefusedError) or (isinstance(cause, OSError) and cause.errno == errno.ECONNREFUSED):
                    return False
                if not isinstance(probe_error, CoordinationBusyError):
                    _active_check_failures += 1
                    if _active_check_failures_since == 0:
                        _active_check_failures_since = now
                    # Multiple failures over six seconds tolerate brief scheduling
                    # stalls but bound work against an unreachable managed service.
                    if _active_check_failures >= 3 and now - _active_check_failures_since >= 6:
                        return False
            finally:
                probe.close()
        # Limit outage diagnostics to twice per minute per worker.
        if _last_active_check_error_at == 0 or now - _last_active_check_error_at >= 30:
            try:
                jh.terminal_debug(
                    f'Coordinator active-process check failed for {client_id}; keeping the worker active: {type(e).__name__}: {e}'
                )
            except Exception:
                pass
            _last_active_check_error_at = now
        return True
