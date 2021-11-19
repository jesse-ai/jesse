import aioredis
import redis as sync_redis_lib
import simplejson as json
import asyncio
import jesse.helpers as jh
from jesse.libs.custom_json import NpEncoder
import os
from jesse.services.env import ENV_VALUES


async def init_redis():
    return await aioredis.create_redis_pool(
        address=(ENV_VALUES['REDIS_HOST'], ENV_VALUES['REDIS_PORT']),
        password=ENV_VALUES['REDIS_PASSWORD'] or None,
    )


async_redis = None
sync_redis = None
if jh.is_jesse_project():
    async_redis = asyncio.run(init_redis())
    sync_redis = sync_redis_lib.Redis(
        host=ENV_VALUES['REDIS_HOST'], port=ENV_VALUES['REDIS_PORT'], db=0,
        password=ENV_VALUES['REDIS_PASSWORD'] if ENV_VALUES['REDIS_PASSWORD'] else None
    )


def sync_publish(event: str, msg):
    if jh.is_unit_testing():
        raise EnvironmentError('sync_publish() should be NOT called during testing. There must be something wrong')

    sync_redis.publish(
        'channel:1', json.dumps({
            'id': os.getpid(),
            'event': f'{jh.app_mode()}.{event}',
            'data': msg
        }, ignore_nan=True, cls=NpEncoder)
    )


async def async_publish(event: str, msg):
    await async_redis.publish(
        'channel:1', json.dumps({
            'id': os.getpid(),
            'event': f'{jh.app_mode()}.{event}',
            'data': msg
        }, ignore_nan=True, cls=NpEncoder)
    )


def process_status(pid=None) -> str:
    if jh.is_unit_testing():
        raise EnvironmentError('process_status() is not meant to be called in unit tests')

    if pid is None:
        pid = jh.get_pid()

    key = f'process-status:{pid}'

    res: str = jh.str_or_none(sync_redis.get(key))
    if res is None:
        raise ValueError(f'No value exists in Redis for process ID of: {pid}')

    return jh.string_after_character(res, ':')
