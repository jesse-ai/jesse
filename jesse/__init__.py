import asyncio
import json
import warnings
import click
import pkg_resources
from fastapi import Query
from starlette.websockets import WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from jesse.services import auth as authenticator
from jesse.services.multiprocessing import process_manager
from jesse.services.redis import async_redis
from jesse.services.web import fastapi_app
import uvicorn
from asyncio import Queue
import jesse.helpers as jh
import time

# to silent stupid pandas warnings
warnings.simplefilter(action='ignore', category=FutureWarning)


JESSE_DIR = pkg_resources.resource_filename(__name__, '')


# load homepage
@fastapi_app.get("/")
async def index():
    return FileResponse(f"{JESSE_DIR}/static/index.html")


# Import and include routers
from jesse.controllers.optimization_controller import router as optimization_router
from jesse.controllers.exchange_controller import router as exchange_router
from jesse.controllers.backtest_controller import router as backtest_router
from jesse.controllers.candles_controller import router as candles_router
from jesse.controllers.strategy_controller import router as strategy_router
from jesse.controllers.auth_controller import router as auth_router
from jesse.controllers.config_controller import router as config_router
from jesse.controllers.notification_controller import router as notification_router
from jesse.controllers.system_controller import router as system_router
from jesse.controllers.file_controller import router as file_router

# register routers
fastapi_app.include_router(optimization_router)
fastapi_app.include_router(exchange_router)
fastapi_app.include_router(backtest_router)
fastapi_app.include_router(candles_router)
fastapi_app.include_router(strategy_router)
fastapi_app.include_router(auth_router)
fastapi_app.include_router(config_router)
fastapi_app.include_router(notification_router)
fastapi_app.include_router(system_router)
fastapi_app.include_router(file_router)


@fastapi_app.websocket("/ws")
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

# create a Click group
@click.group()
@click.version_option(pkg_resources.get_distribution("jesse").version)
def cli() -> None:
    pass


@cli.command()
@click.option(
    '--strict/--no-strict', default=True,
    help='Default is the strict mode which will raise an exception if the values for license is not set.'
)
def install_live(strict: bool) -> None:
    from jesse.services.installer import install
    install(is_live_plugin_already_installed=jh.has_live_trade_plugin(), strict=strict)


@cli.command()
def run() -> None:
    jh.validate_cwd()

    # run all the db migrations
    from jesse.services.migrator import run as run_migrations
    import peewee
    try:
        run_migrations()
    except peewee.OperationalError:
        sleep_seconds = 10
        print(f"Database wasn't ready. Sleep for {sleep_seconds} seconds and try again.")
        time.sleep(sleep_seconds)
        run_migrations()

    # read port from .env file, if not found, use default
    from jesse.services.env import ENV_VALUES
    if 'APP_PORT' in ENV_VALUES:
        port = int(ENV_VALUES['APP_PORT'])
    else:
        port = 9000

    if 'APP_HOST' in ENV_VALUES:
        host = ENV_VALUES['APP_HOST']
    else:
        host = "0.0.0.0"

    # run the main application
    process_manager.flush()
    uvicorn.run(fastapi_app, host=host, port=port, log_level="info")


@fastapi_app.on_event("shutdown")
def shutdown_event():
    from jesse.services.db import database
    database.close_connection()


# # # # # # # # # # # # # # # # # # # # # # # # # # # #
# Live Plugin Endpoints
# # # # # # # # # # # # # # # # # # # # # # # # # # # #
if jh.has_live_trade_plugin():
    from jesse.controllers.live_controller import router as live_router
    fastapi_app.include_router(live_router)


# Mount static files.Must be loaded at the end to prevent overlapping with API endpoints
fastapi_app.mount("/", StaticFiles(directory=f"{JESSE_DIR}/static"), name="static")
