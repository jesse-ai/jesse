import asyncio
import json
import os
import warnings
from typing import Optional
import click
import pkg_resources
from fastapi import BackgroundTasks, Query, Header
from starlette.websockets import WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from jesse.services import auth as authenticator
from jesse.services.multiprocessing import process_manager
from jesse.services.redis import async_redis, async_publish, sync_publish
from jesse.services.web import fastapi_app, BacktestRequestJson, ImportCandlesRequestJson, CancelRequestJson, \
    LoginRequestJson, ConfigRequestJson, LoginJesseTradeRequestJson, NewStrategyRequestJson, FeedbackRequestJson, \
    ReportExceptionRequestJson, OptimizationRequestJson, StoreExchangeApiKeyRequestJson, \
    DeleteExchangeApiKeyRequestJson, StoreNotificationApiKeyRequestJson, DeleteNotificationApiKeyRequestJson, \
    ExchangeSupportedSymbolsRequestJson, SaveStrategyRequestJson, GetStrategyRequestJson, DeleteStrategyRequestJson
import uvicorn
from asyncio import Queue
import jesse.helpers as jh
import time

# to silent stupid pandas warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

# variable to know if the live trade plugin is installed
HAS_LIVE_TRADE_PLUGIN = True
try:
    import jesse_live
except ModuleNotFoundError:
    HAS_LIVE_TRADE_PLUGIN = False


def validate_cwd() -> None:
    """
    make sure we're in a Jesse project
    """
    if not jh.is_jesse_project():
        print(
            jh.color(
                'Current directory is not a Jesse project. You must run commands from the root of a Jesse project. Read this page for more info: https://docs.jesse.trade/docs/getting-started/#create-a-new-jesse-project',
                'red'
            )
        )
        os._exit(1)


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

    await websocket.accept()

    queue = Queue()
    ch, = await async_redis.psubscribe(f"{ENV_VALUES['APP_PORT']}:channel:*")

    async def echo(q):
        while True:
            msg = await q.get()
            msg = json.loads(msg)
            msg['id'] = process_manager.get_client_id(msg['id'])
            await websocket.send_json(
                msg
            )

    async def reader(channel, q):
        async for ch, message in channel.iter():
            # modify id and set the one that the font-end knows
            await q.put(message)

    asyncio.get_running_loop().create_task(reader(ch, queue))
    asyncio.get_running_loop().create_task(echo(queue))

    try:
        while True:
            # just so WebSocketDisconnect would be raised on connection close
            await websocket.receive_text()
    except WebSocketDisconnect:
        await async_redis.punsubscribe(f"{ENV_VALUES['APP_PORT']}:channel:*")
        print('Websocket disconnected')


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
    install(HAS_LIVE_TRADE_PLUGIN, strict)


@cli.command()
def run() -> None:
    validate_cwd()

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

    # run the main application
    process_manager.flush()
    uvicorn.run(fastapi_app, host="0.0.0.0", port=port, log_level="info")


@fastapi_app.post('/general-info')
def general_info(authorization: Optional[str] = Header(None)) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services.general_info import get_general_info

    try:
        data = get_general_info(has_live=HAS_LIVE_TRADE_PLUGIN)
    except Exception as e:
        jh.error(str(e))
        return JSONResponse({
            'error': str(e)
        }, status_code=500)

    return JSONResponse(
        data,
        status_code=200
    )


@fastapi_app.post('/exchange-supported-symbols')
def exchange_supported_symbols(request_json: ExchangeSupportedSymbolsRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.controllers.exchange_info import get_exchange_supported_symbols
    return get_exchange_supported_symbols(request_json.exchange)


@fastapi_app.post('/import-candles')
def import_candles(request_json: ImportCandlesRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
    validate_cwd()

    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.modes import import_candles_mode

    process_manager.add_task(
        import_candles_mode.run, request_json.id, request_json.exchange, request_json.symbol,
        request_json.start_date
    )

    return JSONResponse({'message': 'Started importing candles...'}, status_code=202)


@fastapi_app.post("/cancel-import-candles")
def cancel_import_candles(request_json: CancelRequestJson, authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    process_manager.cancel_process(request_json.id)

    return JSONResponse({'message': f'Candles process with ID of {request_json.id} was requested for termination'},
                        status_code=202)


@fastapi_app.post("/backtest")
def backtest(request_json: BacktestRequestJson, authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    validate_cwd()

    from jesse.modes.backtest_mode import run as run_backtest

    process_manager.add_task(
        run_backtest,
        request_json.id,
        request_json.debug_mode,
        request_json.config,
        request_json.exchange,
        request_json.routes,
        request_json.data_routes,
        request_json.start_date,
        request_json.finish_date,
        None,
        request_json.export_chart,
        request_json.export_tradingview,
        request_json.export_full_reports,
        request_json.export_csv,
        request_json.export_json,
        request_json.fast_mode,
        request_json.benchmark
    )

    return JSONResponse({'message': 'Started backtesting...'}, status_code=202)


@fastapi_app.post("/optimization")
async def optimization(request_json: OptimizationRequestJson, authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    validate_cwd()

    from jesse.modes.optimize_mode import run as run_optimization

    process_manager.add_task(
        run_optimization,
        request_json.id,
        request_json.debug_mode,
        request_json.config,
        request_json.exchange,
        request_json.routes,
        request_json.data_routes,
        request_json.start_date,
        request_json.finish_date,
        request_json.optimal_total,
        request_json.export_csv,
        request_json.export_json,
        request_json.fast_mode,
    )

    return JSONResponse({'message': 'Started optimization...'}, status_code=202)


@fastapi_app.post("/cancel-optimization")
def cancel_optimization(request_json: CancelRequestJson, authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    process_manager.cancel_process(request_json.id)

    return JSONResponse({'message': f'Optimization process with ID of {request_json.id} was requested for termination'},
                        status_code=202)


@fastapi_app.get("/download/{mode}/{file_type}/{session_id}")
def download(mode: str, file_type: str, session_id: str, token: str = Query(...)):
    """
    Log files require session_id because there is one log per each session. Except for the optimize mode
    """
    if not authenticator.is_valid_token(token):
        return authenticator.unauthorized_response()

    from jesse.modes import data_provider

    return data_provider.download_file(mode, file_type, session_id)


@fastapi_app.get("/download/optimize/log")
def download_optimization_log(token: str = Query(...)):
    """
    Optimization logs don't have have session ID
    """
    if not authenticator.is_valid_token(token):
        return authenticator.unauthorized_response()

    from jesse.modes import data_provider

    return data_provider.download_file('optimize', 'log')


@fastapi_app.post("/cancel-backtest")
def cancel_backtest(request_json: CancelRequestJson, authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    process_manager.cancel_process(request_json.id)

    return JSONResponse({'message': f'Backtest process with ID of {request_json.id} was requested for termination'},
                        status_code=202)


@fastapi_app.on_event("shutdown")
def shutdown_event():
    from jesse.services.db import database
    database.close_connection()


@fastapi_app.post("/active-workers")
def active_workers(authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    return JSONResponse({
        'data': list(process_manager.active_workers)
    }, status_code=200)


@fastapi_app.get('/exchange-api-keys')
def get_exchange_api_keys(authorization: Optional[str] = Header(None)) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.modes.exchange_api_keys import get_exchange_api_keys

    return get_exchange_api_keys()


@fastapi_app.post('/exchange-api-keys/store')
def store_exchange_api_keys(json_request: StoreExchangeApiKeyRequestJson,
                            authorization: Optional[str] = Header(None)) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.modes.exchange_api_keys import store_exchange_api_keys

    return store_exchange_api_keys(
        json_request.exchange, json_request.name, json_request.api_key, json_request.api_secret,
        json_request.additional_fields, json_request.general_notifications_id, json_request.error_notifications_id
    )


@fastapi_app.post('/exchange-api-keys/delete')
def delete_exchange_api_keys(json_request: DeleteExchangeApiKeyRequestJson,
                             authorization: Optional[str] = Header(None)) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.modes.exchange_api_keys import delete_exchange_api_keys

    return delete_exchange_api_keys(json_request.id)


@fastapi_app.get('/notification-api-keys')
def get_notification_api_keys(authorization: Optional[str] = Header(None)) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.modes.notification_api_keys import get_notification_api_keys

    return get_notification_api_keys()


@fastapi_app.post('/notification-api-keys/store')
def store_notification_api_keys(
        json_request: StoreNotificationApiKeyRequestJson,
        authorization: Optional[str] = Header(None)
) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.modes.notification_api_keys import store_notification_api_keys

    return store_notification_api_keys(
        json_request.name, json_request.driver, json_request.fields
    )


@fastapi_app.post('/notification-api-keys/delete')
def delete_notification_api_keys(
        json_request: DeleteNotificationApiKeyRequestJson,
        authorization: Optional[str] = Header(None)
) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.modes.notification_api_keys import delete_notification_api_keys

    return delete_notification_api_keys(json_request.id)


@fastapi_app.get('/get-strategies')
def get_strategies(authorization: Optional[str] = Header(None)) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services import strategy_handler
    return strategy_handler.get_strategies()


@fastapi_app.post('/get-strategy')
def get_strategy(
        json_request: GetStrategyRequestJson,
        authorization: Optional[str] = Header(None)
) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services import strategy_handler
    return strategy_handler.get_strategy(json_request.name)


@fastapi_app.post('/save-strategy')
def save_strategy(
        json_request: SaveStrategyRequestJson,
        authorization: Optional[str] = Header(None)
) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services import strategy_handler
    return strategy_handler.save_strategy(json_request.name, json_request.content)


@fastapi_app.post('/delete-strategy')
def delete_strategy(
        json_request: DeleteStrategyRequestJson,
        authorization: Optional[str] = Header(None)
) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services import strategy_handler
    return strategy_handler.delete_strategy(json_request.name)


# def download_optimization_log(token: str = Query(...)):
#     """
#     Optimization logs don't have have session ID
#     """
#     if not authenticator.is_valid_token(token):
#         return authenticator.unauthorized_response()
#
#     from jesse.modes import data_provider
#
#     return data_provider.download_file('optimize', 'log')


# # # # # # # # # # # # # # # # # # # # # # # # # # # #
# Live Plugin Endpoints
# # # # # # # # # # # # # # # # # # # # # # # # # # # #
if HAS_LIVE_TRADE_PLUGIN:
    from jesse.services.web import fastapi_app, LiveRequestJson, LiveCancelRequestJson, GetCandlesRequestJson, \
        GetLogsRequestJson, GetOrdersRequestJson
    from jesse.services import auth as authenticator

    @fastapi_app.post("/live")
    def live(request_json: LiveRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
        if not authenticator.is_valid_token(authorization):
            return authenticator.unauthorized_response()

        validate_cwd()

        trading_mode = 'livetrade' if request_json.paper_mode is False else 'papertrade'

        # execute live session
        from jesse_live import live_mode
        process_manager.add_task(
            live_mode.run,
            request_json.id,
            request_json.debug_mode,
            request_json.exchange,
            request_json.exchange_api_key_id,
            request_json.notification_api_key_id,
            request_json.config,
            request_json.routes,
            request_json.data_routes,
            trading_mode,
        )

        mode = 'live' if request_json.paper_mode is False else 'paper'
        return JSONResponse({'message': f"Started {mode} trading..."}, status_code=202)

    @fastapi_app.post("/cancel-live")
    def cancel_live(request_json: LiveCancelRequestJson, authorization: Optional[str] = Header(None)):
        if not authenticator.is_valid_token(authorization):
            return authenticator.unauthorized_response()

        process_manager.cancel_process(request_json.id)

        return JSONResponse({'message': f'Live process with ID of {request_json.id} terminated.'}, status_code=200)

    @fastapi_app.post('/get-candles')
    def get_candles(json_request: GetCandlesRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
        if not authenticator.is_valid_token(authorization):
            return authenticator.unauthorized_response()

        from jesse import validate_cwd

        validate_cwd()

        from jesse.modes.data_provider import get_candles as gc

        arr = gc(json_request.exchange, json_request.symbol, json_request.timeframe)

        return JSONResponse({
            'id': json_request.id,
            'data': arr
        }, status_code=200)

    @fastapi_app.post('/get-logs')
    def get_logs(json_request: GetLogsRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
        if not authenticator.is_valid_token(authorization):
            return authenticator.unauthorized_response()

        from jesse_live.services.data_provider import get_logs as gl

        arr = gl(json_request.id, json_request.type, json_request.start_time)

        return JSONResponse({
            'id': json_request.id,
            'data': arr
        }, status_code=200)

    @fastapi_app.post('/get-orders')
    def get_orders(json_request: GetOrdersRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
        if not authenticator.is_valid_token(authorization):
            return authenticator.unauthorized_response()

        from jesse_live.services.data_provider import get_orders as go

        arr = go(json_request.session_id)

        return JSONResponse({
            'id': json_request.id,
            'data': arr
        }, status_code=200)

# Mount static files.Must be loaded at the end to prevent overlapping with API endpoints
fastapi_app.mount("/", StaticFiles(directory=f"{JESSE_DIR}/static"), name="static")
