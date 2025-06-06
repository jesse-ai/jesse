from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import asyncio
import json
from asyncio import Queue

from jesse.services import auth as authenticator
from jesse.services.redis import async_redis
from jesse.services.multiprocessing import process_manager
import jesse.helpers as jh

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    from jesse.services.env import ENV_VALUES

    if not authenticator.is_valid_token(token):
        return

    await websocket.accept()

    queue = Queue()
    ch, = await async_redis.psubscribe(f"{ENV_VALUES['APP_PORT']}:channel:*")

    async def echo(q):
        try:
            while True:
                msg = await q.get()
                msg = json.loads(msg)
                msg['id'] = process_manager.get_client_id(msg['id'])
                await websocket.send_json(msg)
        except WebSocketDisconnect:
            await async_redis.punsubscribe(f"{ENV_VALUES['APP_PORT']}:channel:*")
            print(jh.color('WebSocket disconnected', 'yellow'))
        except Exception as e:
            print(jh.color(str(e), 'red'))

    async def reader(channel, q):
        async for ch, message in channel.iter():
            await q.put(message)

    asyncio.get_running_loop().create_task(reader(ch, queue))
    asyncio.get_running_loop().create_task(echo(queue))

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await async_redis.punsubscribe(f"{ENV_VALUES['APP_PORT']}:channel:*")
        print(jh.color('WebSocket disconnected', 'yellow'))
