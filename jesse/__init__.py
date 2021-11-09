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
from jesse.services.redis import async_redis, async_publish, sync_publish
from jesse.services.web import fastapi_app, BacktestRequestJson, ImportCandlesRequestJson, CancelRequestJson, \
    LoginRequestJson, ConfigRequestJson, LoginJesseTradeRequestJson, NewStrategyRequestJson, FeedbackRequestJson, \
    ReportExceptionRequestJson, OptimizationRequestJson
import uvicorn
from asyncio import Queue
import jesse.helpers as jh

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
                'Current directory is not a Jesse project. You must run commands from the root of a Jesse project.',
                'red'
            )
        )
        os._exit(1)


# print(os.path.dirname(jesse))
JESSE_DIR = os.path.dirname(os.path.realpath(__file__))


# load homepage
@fastapi_app.get("/")
async def index():
    return FileResponse(f"{JESSE_DIR}/static/index.html")


@fastapi_app.post("/terminate-all")
async def terminate_all(authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services.multiprocessing import process_manager

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

    from jesse.services import strategy_maker
    return strategy_maker.generate(json_request.name)


@fastapi_app.post("/feedback")
def feedback(json_request: FeedbackRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services import jesse_trade
    return jesse_trade.feedback(json_request.description)


@fastapi_app.post("/report-exception")
def report_exception(json_request: ReportExceptionRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services import jesse_trade
    return jesse_trade.report_exception(
        json_request.description, json_request.traceback, json_request.mode, json_request.attach_logs, json_request.session_id
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


@fastapi_app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    from jesse.services.multiprocessing import process_manager

    if not authenticator.is_valid_token(token):
        return

    await websocket.accept()

    queue = Queue()
    ch, = await async_redis.psubscribe('channel:*')

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
        await async_redis.punsubscribe('channel:*')
        print('Websocket disconnected')


# create a Click group
@click.group()
@click.version_option(pkg_resources.get_distribution("jesse").version)
def cli() -> None:
    pass


@cli.command()
def run() -> None:
    validate_cwd()
    uvicorn.run(fastapi_app, host="127.0.0.1", port=8000, log_level="info")


@fastapi_app.post('/general-info')
def general_info(authorization: Optional[str] = Header(None)) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.modes import data_provider

    return JSONResponse(
        data_provider.get_general_info(has_live=HAS_LIVE_TRADE_PLUGIN),
        status_code=200
    )


@fastapi_app.post('/import-candles')
def import_candles(request_json: ImportCandlesRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
    from jesse.services.multiprocessing import process_manager

    validate_cwd()

    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.modes import import_candles_mode

    process_manager.add_task(
        import_candles_mode.run, 'candles-' + str(request_json.id), request_json.exchange, request_json.symbol,
        request_json.start_date, True
    )

    return JSONResponse({'message': 'Started importing candles...'}, status_code=202)


@fastapi_app.delete("/import-candles")
def cancel_import_candles(request_json: CancelRequestJson, authorization: Optional[str] = Header(None)):
    from jesse.services.multiprocessing import process_manager

    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    process_manager.cancel_process('candles-' + request_json.id)

    return JSONResponse({'message': f'Candles process with ID of {request_json.id} was requested for termination'}, status_code=202)


@fastapi_app.post("/backtest")
def backtest(request_json: BacktestRequestJson, authorization: Optional[str] = Header(None)):
    from jesse.services.multiprocessing import process_manager

    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    validate_cwd()

    from jesse.modes.backtest_mode import run as run_backtest

    process_manager.add_task(
        run_backtest,
        'backtest-' + str(request_json.id),
        request_json.debug_mode,
        request_json.config,
        request_json.routes,
        request_json.extra_routes,
        request_json.start_date,
        request_json.finish_date,
        None,
        request_json.export_chart,
        request_json.export_tradingview,
        request_json.export_full_reports,
        request_json.export_csv,
        request_json.export_json
    )

    return JSONResponse({'message': 'Started backtesting...'}, status_code=202)


@fastapi_app.post("/optimization")
async def optimization(request_json: OptimizationRequestJson, authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services.multiprocessing import process_manager

    validate_cwd()

    from jesse.modes.optimize_mode import run as run_optimization

    process_manager.add_task(
        run_optimization,
        'optimize-' + str(request_json.id),
        request_json.debug_mode,
        request_json.config,
        request_json.routes,
        request_json.extra_routes,
        request_json.start_date,
        request_json.finish_date,
        request_json.optimal_total,
        request_json.export_csv,
        request_json.export_json
    )

    # optimize_mode(start_date, finish_date, optimal_total, cpu, csv, json)

    return JSONResponse({'message': 'Started optimization...'}, status_code=202)


@fastapi_app.delete("/optimization")
def cancel_optimization(request_json: CancelRequestJson, authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services.multiprocessing import process_manager

    process_manager.cancel_process('optimize-' + request_json.id)

    return JSONResponse({'message': f'Optimization process with ID of {request_json.id} was requested for termination'}, status_code=202)


@fastapi_app.get("/download/{mode}/{file_type}/{session_id}")
def download(mode: str, file_type: str, session_id: str, token: str = Query(...)):
    if not authenticator.is_valid_token(token):
        return authenticator.unauthorized_response()

    from jesse.modes import data_provider

    return data_provider.download_file(mode, file_type, session_id)


@fastapi_app.delete("/backtest")
def cancel_backtest(request_json: CancelRequestJson, authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services.multiprocessing import process_manager

    process_manager.cancel_process('backtest-' + request_json.id)

    return JSONResponse({'message': f'Backtest process with ID of {request_json.id} was requested for termination'}, status_code=202)


@fastapi_app.on_event("shutdown")
def shutdown_event():
    from jesse.services import db
    db.close_connection()


@cli.command()
@click.argument('name', required=True, type=str)
def make_project(name: str) -> None:
    """
    generates a new strategy folder from jesse/strategies/ExampleStrategy
    """
    from jesse.config import config
    from jesse.services.failure import register_custom_exception_handler

    config['app']['trading_mode'] = 'make-project'

    register_custom_exception_handler()

    from jesse.services import project_maker

    project_maker.generate(name)


@cli.command()
def migrate() -> None:
    """
    Runs the database migrations to make sure no columns are missing
    """
    from jesse.services.migrator import run
    run()


@fastapi_app.post("/login-jesse-trade")
def login_jesse_trade(json_request: LoginJesseTradeRequestJson, authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services import auth

    return auth.login_to_jesse_trade(json_request.email, json_request.password)


@fastapi_app.post("/logout-jesse-trade")
def logout_jesse_trade(authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services import auth

    return auth.logout_from_jesse_trade()


if HAS_LIVE_TRADE_PLUGIN:
    # load live trade related functions from the live trade plugin
    from jesse_live.web_routes import live, get_candles, get_logs, get_orders


# Mount static files.Must be loaded at the end to prevent overlapping with API endpoints
fastapi_app.mount("/", StaticFiles(directory=f"{JESSE_DIR}/static"), name="static")
