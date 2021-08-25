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
        password=ENV_VALUES['REDIS_PASSWORD'] if ENV_VALUES['REDIS_PASSWORD'] else None
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
