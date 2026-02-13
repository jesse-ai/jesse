"""
Jesse MCP WebSocket Event Listener

This module provides real-time event listening capabilities for the MCP server.
It connects to Jesse's WebSocket endpoint and stores events by category for
real-time access by MCP tools.

EVENT CATEGORIES:
- backtest: Backtest-related events (progressbar, metrics, alerts, etc.)
- candles: Candle import events (progressbar, alerts, exceptions)

USAGE:
    from jesse.mcp.ws_listener import start_listener, register_callback, is_connected

    # Start listener (call once at server startup)
    start_listener(api_url="http://localhost:9000", password="your_password")

    # Register callbacks for real-time event processing
    def handle_backtest_event(event):
        print(f"Backtest event: {event}")

    def handle_candle_event(event):
        print(f"Candle event: {event}")

    register_callback("backtest", handle_backtest_event)
    register_callback("candles", handle_candle_event)
"""

import asyncio
import threading
import websockets
import json
import time
from collections import deque
from hashlib import sha256
from typing import Dict, List, Any, Optional

# Pure real-time event callbacks (dashboard-style: listen and forget)
# No event storage - monitoring functions maintain their own local state
from typing import Callable
EVENT_CALLBACKS: Dict[str, List[Callable]] = {
    'backtest': [],
    'candles': [],
}

# Connection status
_connected = False
_connection_thread: Optional[threading.Thread] = None
_api_url: Optional[str] = None
_password: Optional[str] = None


def register_callback(category: str, callback: Callable) -> None:
    """
    Register a callback function for a specific event category.

    Args:
        category: Event category ('backtest' or 'candles')
        callback: Function to call when events arrive (receives event dict)
    """
    if category not in EVENT_CALLBACKS:
        EVENT_CALLBACKS[category] = []
    EVENT_CALLBACKS[category].append(callback)


def unregister_callback(category: str, callback: Callable) -> None:
    """
    Unregister a callback function.

    Args:
        category: Event category
        callback: Callback function to remove
    """
    if category in EVENT_CALLBACKS:
        try:
            EVENT_CALLBACKS[category].remove(callback)
        except ValueError:
            pass  # Callback not found

def start_listener(api_url: str, password: str) -> bool:
    """
    Start the WebSocket event listener in a background thread.

    Args:
        api_url: Jesse API URL (e.g., "http://localhost:9000")
        password: Jesse admin password

    Returns:
        bool: True if listener started, False if already running
    """
    global _connection_thread, _api_url, _password

    if _connection_thread and _connection_thread.is_alive():
        return False  # Already running

    _api_url = api_url
    _password = password

    _connection_thread = threading.Thread(
        target=_run_async_loop,
        args=(api_url, password),
        daemon=True,
        name="mcp-ws-listener"
    )
    _connection_thread.start()

    # Wait a moment for connection to establish
    time.sleep(0.5)

    return True

def stop_listener() -> bool:
    """
    Stop the WebSocket listener.

    Returns:
        bool: True if stopped, False if not running
    """
    global _connection_thread, _connected

    if not _connection_thread or not _connection_thread.is_alive():
        return False

    _connected = False
    # Thread will stop when connection is closed
    return True

def is_connected() -> bool:
    """Check if WebSocket is currently connected."""
    return _connected



def _run_async_loop(api_url: str, password: str):
    """Run the asyncio event loop in a thread."""
    try:
        asyncio.run(_websocket_listener(api_url, password))
    except Exception as e:
        print(f"WebSocket listener thread error: {e}")

async def _websocket_listener(api_url: str, password: str):
    """
    Main WebSocket listener function with auto-reconnection.
    """
    global _connected

    while True:  # Auto-reconnection loop
        try:
            # Build WebSocket URL
            if api_url.startswith('http://'):
                ws_url = api_url.replace('http://', 'ws://') + '/ws'
            elif api_url.startswith('https://'):
                ws_url = api_url.replace('https://', 'wss://') + '/ws'
            else:
                print(f"Invalid API URL format: {api_url}")
                await asyncio.sleep(30)
                continue

            # Generate auth token
            auth_token = sha256(password.encode('utf-8')).hexdigest()
            ws_url += f'?token={auth_token}'

            print(f"🔌 Connecting to Jesse WebSocket: {ws_url}")

            async with websockets.connect(ws_url) as websocket:
                _connected = True
                print("✅ MCP WebSocket connected to Jesse backend")

                async for message in websocket:
                    try:
                        # Parse the message
                        data = json.loads(message)

                        # Add timestamp for sorting
                        data['timestamp'] = time.time()

                        # Store minimal history and call callbacks (hybrid approach)
                        event_type = data.get('event', '')
                        event_id = str(data.get('id', ''))

                        # Pure callback-based (no storage) - dashboard approach
                        if event_type.startswith('backtest.') and event_id:
                            for callback in EVENT_CALLBACKS['backtest']:
                                try:
                                    callback(data)
                                except Exception as e:
                                    print(f"Error in backtest callback: {e}")
                        elif event_type.startswith('candles.') and event_id:
                            for callback in EVENT_CALLBACKS['candles']:
                                try:
                                    callback(data)
                                except Exception as e:
                                    print(f"Error in candles callback: {e}")
                        # Ignore other event types or events without ID

                    except json.JSONDecodeError as e:
                        print(f"Failed to parse WebSocket message: {e}")
                        continue
                    except Exception as e:
                        print(f"Error processing WebSocket message: {e}")
                        continue

        except websockets.exceptions.ConnectionClosed:
            print("🔌 WebSocket connection closed, reconnecting...")
        except Exception as e:
            print(f"🔌 WebSocket connection error: {e}")
        finally:
            _connected = False

        # Wait before reconnecting
        print("⏳ Reconnecting in 5 seconds...")
        await asyncio.sleep(5)

