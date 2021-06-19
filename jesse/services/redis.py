import aioredis
import redis as sync_redis_lib
import simplejson as json
import asyncio


async def init_redis():
    return await aioredis.create_redis_pool('redis://localhost')


async_redis = asyncio.run(init_redis())
sync_redis = sync_redis_lib.Redis(host='localhost', port=6379, db=0)


def sync_publish(msg: dict):
    if type(msg) is not dict:
        raise TypeError('broadcasting message must be a dict')

    sync_redis.publish('channel:1', json.dumps(msg, ignore_nan=True))


async def async_publish(msg: dict):
    if type(msg) is not dict:
        raise TypeError('broadcasting message must be a dict')

    await async_redis.publish('channel:1', json.dumps(msg, ignore_nan=True))

