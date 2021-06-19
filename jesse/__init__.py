import asyncio
import json
import os
import sys
import warnings
from pydoc import locate
import click
import pkg_resources
from fastapi import BackgroundTasks
from starlette.websockets import WebSocket
from fastapi.responses import JSONResponse
from jesse.services.redis import async_redis, async_publish, sync_publish
from jesse.services.web import fastapi_app
from jesse.services.failure import register_custom_exception_handler
import uvicorn
from asyncio import Queue
from jesse.services.multiprocessing import process_manager
import jesse.helpers as jh
from jesse.services import db


# to silent stupid pandas warnings
warnings.simplefilter(action='ignore', category=FutureWarning)
# fix directory issue
sys.path.insert(0, os.getcwd())
ls = os.listdir('.')
is_jesse_project = 'strategies' in ls and 'config.py' in ls and 'storage' in ls and 'routes.py' in ls


def validate_cwd() -> None:
    """
    make sure we're in a Jesse project
    """
    if not is_jesse_project:
        print(
            jh.color(
                'Current directory is not a Jesse project. You must run commands from the root of a Jesse project.',
                'red'
            )
        )
        os._exit(1)


def inject_local_config() -> None:
    """
    injects config from local config file
    """
    local_config = locate('config.config')
    from jesse.config import set_config
    set_config(local_config)


def inject_local_routes() -> None:
    """
    injects routes from local routes folder
    """
    local_router = locate('routes')
    from jesse.routes import router

    router.set_routes(local_router.routes)
    router.set_extra_candles(local_router.extra_candles)


# inject local files
if is_jesse_project:
    inject_local_config()
    inject_local_routes()


@fastapi_app.get("/terminate-all")
async def terminate_all():
    from jesse.services.multiprocessing import process_manager

    process_manager.flush()
    return JSONResponse({'message': 'terminating all tasks...'})


@fastapi_app.get("/shutdown")
async def shutdown(background_tasks: BackgroundTasks):
    background_tasks.add_task(jh.terminate_app)
    return JSONResponse({'message': 'Shutting down...'})


@fastapi_app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    queue = Queue()
    ch, = await async_redis.psubscribe('channel:*')

    async def reader(channel):
        async for ch, message in channel.iter():
            await queue.put(message)

    asyncio.get_running_loop().create_task(reader(ch))

    while True:
        await websocket.send_json(json.loads(await queue.get()))


# create a Click group
@click.group()
@click.version_option(pkg_resources.get_distribution("jesse").version)
def cli() -> None:
    pass


@cli.command()
def run() -> None:
    validate_cwd()
    uvicorn.run(fastapi_app, host="127.0.0.1", port=8000, log_level="info")


@cli.command()
@click.argument('exchange', required=True, type=str)
@click.argument('symbol', required=True, type=str)
@click.argument('start_date', required=True, type=str)
@click.option('--skip-confirmation', is_flag=True,
              help="Will prevent confirmation for skipping duplicates")
def import_candles(exchange: str, symbol: str, start_date: str, skip_confirmation: bool) -> None:
    """
    imports historical candles from exchange
    """
    validate_cwd()
    from jesse.config import config
    config['app']['trading_mode'] = 'import-candles'

    register_custom_exception_handler()

    from jesse.services import db

    from jesse.modes import import_candles_mode

    import_candles_mode.run(exchange, symbol, start_date, skip_confirmation)

    db.close_connection()


@fastapi_app.get("/backtest")
def backtest(
        start_date: str,
        finish_date: str,
        debug_mode: bool,
        export_csv: bool,
        export_json: bool,
        export_chart: bool,
        export_tradingview: bool,
        export_full_reports: bool
) -> JSONResponse:
    validate_cwd()

    from jesse.modes.backtest_mode import run as run_backtest

    process_manager.add_task(
        run_backtest, debug_mode, start_date, finish_date, None, export_chart,
        export_tradingview, export_full_reports, export_csv, export_json
    )

    return JSONResponse({'message': 'Started backtesting...'}, status_code=202)


@fastapi_app.on_event("shutdown")
def shutdown_event():
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


live_package_exists = True
try:
    import jesse_live
except ModuleNotFoundError:
    live_package_exists = False
if live_package_exists:
    from jesse_live.web_routes import paper, live


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
