import aioredis
import redis as sync_redis_lib
import simplejson as json
import asyncio
import jesse.helpers as jh
from jesse.libs.custom_json import NpEncoder
import os


async def init_redis():
    return await aioredis.create_redis_pool('redis://localhost')


async_redis = asyncio.run(init_redis())
sync_redis = sync_redis_lib.Redis(host='localhost', port=6379, db=0)


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
