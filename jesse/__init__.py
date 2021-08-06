import asyncio
import json
import os
import sys
import warnings
from typing import Optional

import click
import pkg_resources
from fastapi import BackgroundTasks, Cookie, Query, Header
from starlette import status
from starlette.websockets import WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from jesse.services import auth as authenticator
from jesse.services.redis import async_redis, async_publish, sync_publish
from jesse.services.web import fastapi_app, BacktestRequestJson, ImportCandlesRequestJson, CancelRequestJson, \
    GetCandlesRequestJson, LoginRequestJson
from jesse.services.failure import register_custom_exception_handler
import uvicorn
from asyncio import Queue
from jesse.services.multiprocessing import process_manager
import jesse.helpers as jh


# to silent stupid pandas warnings
warnings.simplefilter(action='ignore', category=FutureWarning)
# fix directory issue
sys.path.insert(0, os.getcwd())
ls = os.listdir('.')
IS_JESSE_PROJECT = 'strategies' in ls and 'config.py' in ls and 'storage' in ls and 'routes.py' in ls

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
    if not IS_JESSE_PROJECT:
        print(
            jh.color(
                'Current directory is not a Jesse project. You must run commands from the root of a Jesse project.',
                'red'
            )
        )
        os._exit(1)


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


@fastapi_app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
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


@fastapi_app.post('/routes-info')
def available_exchanges(authorization: Optional[str] = Header(None)) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    validate_cwd()

    from jesse.modes import data_provider

    return JSONResponse({
        'data': data_provider.available_routes_inputs(has_live=HAS_LIVE_TRADE_PLUGIN)
    }, status_code=200)


@fastapi_app.post('/import-candles')
def import_candles(request_json: ImportCandlesRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
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
def cancel_backtest(request_json: CancelRequestJson, authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    process_manager.cancel_process('candles-' + request_json.id)

    return JSONResponse({'message': f'Candles process with ID of {request_json.id} terminated.'}, status_code=200)


@fastapi_app.post("/backtest")
def backtest(request_json: BacktestRequestJson, authorization: Optional[str] = Header(None)):
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


@fastapi_app.delete("/backtest")
def cancel_backtest(request_json: CancelRequestJson, authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    process_manager.cancel_process('backtest-' + request_json.id)

    return JSONResponse({'message': f'Backtest process with ID of {request_json.id} terminated.'}, status_code=200)


@fastapi_app.on_event("shutdown")
def shutdown_event():
    from jesse.services import db
    db.close_connection()


@cli.command()
@click.argument('start_date', required=True, type=str)
@click.argument('finish_date', required=True, type=str)
@click.argument('optimal_total', required=True, type=int)
@click.option(
    '--cpu', default=0, show_default=True,
    help='The number of CPU cores that Jesse is allowed to use. If set to 0, it will use as many as is available on your machine.')
@click.option(
    '--debug/--no-debug', default=False,
    help='Displays detailed logs about the genetics algorithm. Use it if you are interested int he genetics algorithm.'
)
@click.option('--csv/--no-csv', default=False, help='Outputs a CSV file of all DNAs on completion.')
@click.option('--json/--no-json', default=False, help='Outputs a JSON file of all DNAs on completion.')
def optimize(start_date: str, finish_date: str, optimal_total: int, cpu: int, debug: bool, csv: bool,
             json: bool) -> None:
    """
    tunes the hyper-parameters of your strategy
    """
    validate_cwd()
    from jesse.config import config
    config['app']['trading_mode'] = 'optimize'

    register_custom_exception_handler()

    # debug flag
    config['app']['debug_mode'] = debug

    from jesse.modes.optimize_mode import optimize_mode

    optimize_mode(start_date, finish_date, optimal_total, cpu, csv, json)


@cli.command()
@click.argument('name', required=True, type=str)
def make_strategy(name: str) -> None:
    """
    generates a new strategy folder from jesse/strategies/ExampleStrategy
    """
    validate_cwd()
    from jesse.config import config

    config['app']['trading_mode'] = 'make-strategy'

    register_custom_exception_handler()

    from jesse.services import strategy_maker

    strategy_maker.generate(name)


@cli.command()
@click.argument('name', required=True, type=str)
def make_project(name: str) -> None:
    """
    generates a new strategy folder from jesse/strategies/ExampleStrategy
    """
    from jesse.config import config

    config['app']['trading_mode'] = 'make-project'

    register_custom_exception_handler()

    from jesse.services import project_maker

    project_maker.generate(name)


@cli.command()
@click.option('--dna/--no-dna', default=False,
              help='Translates DNA into parameters. Used in optimize mode only')
def routes(dna: bool) -> None:
    """
    lists all routes
    """
    validate_cwd()
    from jesse.config import config

    config['app']['trading_mode'] = 'routes'

    register_custom_exception_handler()

    from jesse.modes import routes_mode

    routes_mode.run(dna)


if HAS_LIVE_TRADE_PLUGIN:
    from jesse_live.web_routes import live

    @fastapi_app.post('/get-candles')
    def get_candles(json_request: GetCandlesRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
        if not authenticator.is_valid_token(authorization):
            return authenticator.unauthorized_response()

        validate_cwd()

        from jesse.modes.data_provider import get_candles

        arr = get_candles(json_request.exchange, json_request.symbol, json_request.timeframe)

        return JSONResponse({
            'id': json_request.id,
            'data': arr
        }, status_code=200)


    @cli.command()
    @click.option('--email', prompt='Email')
    @click.option('--password', prompt='Password', hide_input=True)
    def login(email, password) -> None:
        """
        (Initially) Logins to the website.
        """
        validate_cwd()

        # set trading mode
        from jesse.config import config
        config['app']['trading_mode'] = 'login'

        register_custom_exception_handler()

        from jesse_live.auth import login

        login(email, password)
