import aioredis
import redis as sync_redis_lib
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
    TimeoutError as RedisTimeoutError,
)
import simplejson as json
import asyncio
import time
import jesse.helpers as jh
from jesse.libs.custom_json import NpEncoder
import os
import base64
from jesse.services.env import ENV_VALUES


async def init_redis():
    return await aioredis.create_redis_pool(
        address=(ENV_VALUES['REDIS_HOST'], ENV_VALUES['REDIS_PORT']),
        password=ENV_VALUES['REDIS_PASSWORD'] or None,
        db=int(ENV_VALUES.get('REDIS_DB') or 0),
    )


async_redis = None
sync_redis = None
_last_active_check_error_at = 0
if jh.is_jesse_project():
    if not jh.is_notebook():
        async_redis = asyncio.run(init_redis())
        sync_redis = sync_redis_lib.Redis(
            host=ENV_VALUES['REDIS_HOST'], port=ENV_VALUES['REDIS_PORT'], db=int(ENV_VALUES.get('REDIS_DB') or 0),
            password=ENV_VALUES['REDIS_PASSWORD'] if ENV_VALUES['REDIS_PASSWORD'] else None,
            socket_connect_timeout=1,
            socket_timeout=1,
            health_check_interval=30,
        )


def sync_publish(event: str, msg, compression: bool = False):
    if jh.is_unit_testing():
        raise EnvironmentError('sync_publish() should be NOT called during testing. There must be something wrong')

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
        # Log publish errors so we can diagnose Redis outages without crashing the worker
        jh.terminal_debug(f"Redis publish error: {e}")


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
    Redis key under which a live-trading process stores the full snapshot of
    its strategy-drawn chart data (lines, extra charts, horizontal lines).
    Written by jesse-live's dashboard service; read by the API process to
    hydrate the dashboard chart after a page (re)load.
    """
    return f"{ENV_VALUES['APP_PORT']}|live-charts:{session_id}"


def store_live_charts_snapshot(session_id: str, charts: dict) -> bool:
    try:
        sync_redis.set(
            live_charts_key(session_id),
            json.dumps(charts, ignore_nan=True, cls=NpEncoder),
            ex=60 * 60 * 24 * 7
        )
        return True
    except Exception as e:
        jh.terminal_debug(f'Error storing live charts snapshot in Redis: {e}')
        return False


def get_live_charts_snapshot(session_id: str) -> dict:
    try:
        raw = sync_redis.get(live_charts_key(session_id))
        if raw is None:
            return {}
        return json.loads(raw)
    except Exception as e:
        jh.terminal_debug(f'Error loading live charts snapshot from Redis: {e}')
        return {}


def is_process_active(client_id: str) -> bool:
    global _last_active_check_error_at

    if jh.is_unit_testing():
        return False

    try:
        is_active = sync_redis.sismember(f"{ENV_VALUES['APP_PORT']}|active-processes", client_id)
        _last_active_check_error_at = 0
        return is_active
    except (RedisConnectionError, RedisTimeoutError, OSError) as e:
        now = time.monotonic()
        if _last_active_check_error_at == 0 or now - _last_active_check_error_at >= 30:
            try:
                jh.terminal_debug(
                    f'Redis active-process check failed for {client_id}; keeping the worker active: {type(e).__name__}: {e}'
                )
            except Exception:
                pass
            _last_active_check_error_at = now
        return True
