import asyncio
import json
from typing import Set
from starlette.websockets import WebSocket

from jesse.services.redis import async_redis
from jesse.services.multiprocessing import process_manager
import jesse.helpers as jh


class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.is_subscribed = False
        self.redis_subscriber = None
        self.reader_task = None
        
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        
    async def broadcast(self, message: dict):
        # Process id with the manager for each websocket separately
        for connection in self.active_connections:
            message_copy = dict(message)
            message_copy['id'] = process_manager.get_client_id(message_copy['id'])
            await connection.send_json(message_copy)
            
    async def start_redis_listener(self, channel_pattern):
        if not self.is_subscribed:
            self.redis_subscriber, = await async_redis.psubscribe(channel_pattern)
            self.is_subscribed = True
            
            # Start the listener task
            self.reader_task = asyncio.create_task(self._redis_listener(self.redis_subscriber))
            
    async def _redis_listener(self, channel):
        try:
            async for ch, message in channel.iter():
                # Parse the message and broadcast to all clients
                message_dict = json.loads(message)
                await self.broadcast(message_dict)
        except Exception as e:
            print(jh.color(f"Redis listener error: {str(e)}", 'red'))
            
    async def stop_redis_listener(self):
        if self.is_subscribed and len(self.active_connections) == 0:
            # Only unsubscribe if no clients are connected
            if self.reader_task and not self.reader_task.done():
                self.reader_task.cancel()
                
            from jesse.services.env import ENV_VALUES
            await async_redis.punsubscribe(f"{ENV_VALUES['APP_PORT']}:channel:*")
            self.is_subscribed = False
            print(jh.color("Redis unsubscribed - no more active connections", 'yellow'))


# Create a global instance
ws_manager = ConnectionManager()
