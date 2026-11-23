import asyncio

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from jesse.helpers import get_os
from jesse.services import auth as authenticator
from jesse.services.auth import require_auth
from jesse.services.lsp import LSP_HOST, lsp_port, lsp_token

router = APIRouter(prefix='/lsp-config', tags=['LSP Configuration'], dependencies=[Depends(require_auth)])
proxy_router = APIRouter(tags=['LSP Configuration'])


@router.get("")
def get_lsp_config()->JSONResponse:
    # Check if formatting is available on the current platform
    # Formatting is only available on non-windows platforms
    isFormattingAvailable = get_os() != 'windows'

    return JSONResponse(
        {'ws_port': lsp_port(),
         'ws_path': '/lsp',
         # the code editor is reached through the dashboard's own address
         'proxied': True,
         'is_formatting_available': isFormattingAvailable}, status_code=200)


@proxy_router.websocket('/lsp')
async def lsp_proxy(websocket: WebSocket, token: str = Query('')):
    """
    Connects the dashboard's code editor to the code editor server, which listens on this
    machine only. The user's login is checked here, and the server checks its own token.
    """
    if not authenticator.is_valid_link_token(token):
        await websocket.close(code=4401)
        return

    import websockets
    await websocket.accept()
    upstream_url = f'ws://{LSP_HOST}:{lsp_port()}/lsp?token={lsp_token()}'
    try:
        # The editor's messages can be large (a whole file), so there is no size limit.
        async with websockets.connect(upstream_url, max_size=None, open_timeout=10) as upstream:
            async def to_server():
                while True:
                    message = await websocket.receive()
                    if message['type'] == 'websocket.disconnect':
                        return
                    if message.get('text') is not None:
                        await upstream.send(message['text'])
                    elif message.get('bytes') is not None:
                        await upstream.send(message['bytes'])

            async def to_browser():
                async for message in upstream:
                    if isinstance(message, str):
                        await websocket.send_text(message)
                    else:
                        await websocket.send_bytes(message)

            tasks = [asyncio.create_task(to_server()), asyncio.create_task(to_browser())]
            _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
    except (OSError, websockets.exceptions.WebSocketException, WebSocketDisconnect):
        # the code editor server is not running or the connection dropped; the editor reconnects
        pass
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass
