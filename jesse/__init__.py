import warnings
from typing import Optional, Dict, Set
import click
import pkg_resources
from fastapi import BackgroundTasks, Query, Header
from fastapi.responses import JSONResponse, FileResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect
from jesse.services.multiprocessing import process_manager
from jesse.services.web import fastapi_app
from jesse.services.redis import async_redis, async_publish, sync_publish
from jesse.services.web import fastapi_app, BacktestRequestJson, ImportCandlesRequestJson, CancelRequestJson, \
    LoginRequestJson, ConfigRequestJson, LoginJesseTradeRequestJson, NewStrategyRequestJson, FeedbackRequestJson, \
    ReportExceptionRequestJson, OptimizationRequestJson, StoreExchangeApiKeyRequestJson, \
    DeleteExchangeApiKeyRequestJson, StoreNotificationApiKeyRequestJson, DeleteNotificationApiKeyRequestJson, \
    ExchangeSupportedSymbolsRequestJson, SaveStrategyRequestJson, GetStrategyRequestJson, DeleteStrategyRequestJson, \
    DeleteCandlesRequestJson
from jesse.services import auth as authenticator

from jesse.services.ws_manager import ws_manager
import uvicorn
import jesse.helpers as jh
import time

# variable to know if the live trade plugin is installed
HAS_LIVE_TRADE_PLUGIN = True
try:
    import jesse_live
except ModuleNotFoundError:
    HAS_LIVE_TRADE_PLUGIN = False

# to silent stupid pandas warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

# get the jesse directory
JESSE_DIR = pkg_resources.resource_filename(__name__, '')


# load homepage
@fastapi_app.get("/")
async def index():
    return FileResponse(f"{JESSE_DIR}/static/index.html")


@fastapi_app.post("/terminate-all")
async def terminate_all(authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    process_manager.flush()
    return JSONResponse({'message': 'terminating all tasks...'})


@fastapi_app.post("/shutdown")
async def shutdown(background_tasks: BackgroundTasks, authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    background_tasks.add_task(jh.terminate_app)
    return JSONResponse({'message': 'Shutting down...'})


@fastapi_app.post("/auth")
def auth(json_request: LoginRequestJson):
    return authenticator.password_to_token(json_request.password)


@fastapi_app.post("/make-strategy")
def make_strategy(json_request: NewStrategyRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services import strategy_handler
    return strategy_handler.generate(json_request.name)


@fastapi_app.post("/feedback")
def feedback(json_request: FeedbackRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services import jesse_trade
    return jesse_trade.feedback(json_request.description, json_request.email)


@fastapi_app.post("/report-exception")
def report_exception(json_request: ReportExceptionRequestJson,
                     authorization: Optional[str] = Header(None)) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services import jesse_trade
    return jesse_trade.report_exception(
        json_request.description,
        json_request.traceback,
        json_request.mode,
        json_request.attach_logs,
        json_request.session_id,
        json_request.email,
        has_live=HAS_LIVE_TRADE_PLUGIN
    )


@fastapi_app.post("/get-config")
def get_config(json_request: ConfigRequestJson, authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.modes.data_provider import get_config as gc

    return JSONResponse({
        'data': gc(json_request.current_config, has_live=HAS_LIVE_TRADE_PLUGIN)
    }, status_code=200)


@fastapi_app.post("/update-config")
def update_config(json_request: ConfigRequestJson, authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.modes.data_provider import update_config as uc

    uc(json_request.current_config)

    return JSONResponse({'message': 'Updated configurations successfully'}, status_code=200)


@fastapi_app.post("/clear-candles-database-cache")
def clear_candles_database_cache(authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services.cache import cache
    cache.flush()

    return JSONResponse({
        'status': 'success',
        'message': 'Candles database cache cleared successfully',
    }, status_code=200)


@fastapi_app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    from jesse.services.env import ENV_VALUES

    if not authenticator.is_valid_token(token):
        return

    # Use connection manager to handle this websocket
    connection_id = str(id(websocket))
    print(jh.color(f"=> WebSocket {connection_id} connecting", 'yellow'))
    
    await ws_manager.connect(websocket)
    channel_pattern = f"{ENV_VALUES['APP_PORT']}:channel:*"
    
    # Start Redis listener if not already started
    await ws_manager.start_redis_listener(channel_pattern)
    
    try:
        # Keep the connection alive
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        print(jh.color(f"WebSocket {connection_id} disconnected", 'yellow'))
        ws_manager.disconnect(websocket)
        # Optionally stop Redis listener if no more clients
        await ws_manager.stop_redis_listener()
    except Exception as e:
        print(jh.color(f"WebSocket error: {str(e)}", 'red'))
        ws_manager.disconnect(websocket)
        await ws_manager.stop_redis_listener()

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
    # Display welcome message
    welcome_message = """
     ██╗███████╗███████╗███████╗███████╗
     ██║██╔════╝██╔════╝██╔════╝██╔════╝
     ██║█████╗  ███████╗███████╗█████╗  
██   ██║██╔══╝  ╚════██║╚════██║██╔══╝  
╚█████╔╝███████╗███████║███████║███████╗
 ╚════╝ ╚══════╝╚══════╝╚══════╝╚══════╝
                                        
    """
    version = pkg_resources.get_distribution("jesse").version
    print(welcome_message)
    print(f"Main Framework Version: {version}")
    
    # Check if jesse-live is installed and display its version
    if jh.has_live_trade_plugin():
        try:
            from jesse_live.version import __version__ as live_version
            print(f"Live Plugin Version: {live_version}")
        except ImportError:
            pass
    
    jh.validate_cwd()

    print("")

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
# Routes
# # # # # # # # # # # # # # # # # # # # # # # # # # # #
from jesse.controllers.websocket_controller import router as websocket_router
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
fastapi_app.include_router(websocket_router)
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


# # # # # # # # # # # # # # # # # # # # # # # # # # # #
# Live Trade Plugin
# # # # # # # # # # # # # # # # # # # # # # # # # # # #
if jh.has_live_trade_plugin():
    from jesse.controllers.live_controller import router as live_router
    fastapi_app.include_router(live_router)


# # # # # # # # # # # # # # # # # # # # # # # # # # # #
# Static Files (Must be loaded at the end to prevent overlapping with API endpoints)
# # # # # # # # # # # # # # # # # # # # # # # # # # # #
fastapi_app.mount("/", StaticFiles(directory=f"{JESSE_DIR}/static"), name="static")
