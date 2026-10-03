import os
import warnings
from contextlib import asynccontextmanager
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from jesse.services.web import fastapi_app
import jesse.helpers as jh
from jesse.services.auth import InvalidAuthError, unauthorized_response

from jesse.services.e2e_database import reset_test_database_if_requested

reset_test_database_if_requested()

# import cli to register the routes. Do NOT remove this import.
from jesse.cli import cli


@fastapi_app.exception_handler(InvalidAuthError)
async def invalid_auth_exception_handler(_request, _exc):
    return unauthorized_response()


# to silent stupid pandas warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

# get the jesse directory
JESSE_DIR = os.path.dirname(os.path.abspath(__file__))

# define lifespan (replaces deprecated @on_event("shutdown"))
@asynccontextmanager
async def lifespan(app):
    from jesse.services import research_jobs
    research_jobs.accept_jobs()
    yield
    from jesse.services.db import database
    database.close_connection()
    from jesse.services.lsp import terminate_lsp_server
    terminate_lsp_server()
    # Research scripts and analysis jobs run in their own process groups, so they do not
    # receive the terminal's Ctrl+C; stop them explicitly, refusing any job a request was still
    # preparing (research_jobs.shutdown).
    research_jobs.shutdown()

fastapi_app.router.lifespan_context = lifespan

# load homepage
@fastapi_app.get("/")
async def index():
    return FileResponse(f"{JESSE_DIR}/static/index.html")






# # # # # # # # # # # # # # # # # # # # # # # # # # # #
# Routes
# # # # # # # # # # # # # # # # # # # # # # # # # # # #
from jesse.controllers.websocket_controller import router as websocket_router
from jesse.controllers.optimization_controller import router as optimization_router
from jesse.controllers.monte_carlo_controller import router as monte_carlo_router
from jesse.controllers.exchange_controller import router as exchange_router
from jesse.controllers.backtest_controller import router as backtest_router
from jesse.controllers.significance_test_controller import router as significance_test_router
from jesse.controllers.candles_controller import export_router as candles_export_router, router as candles_router
from jesse.controllers.strategy_controller import router as strategy_router
from jesse.controllers.auth_controller import router as auth_router
from jesse.controllers.config_controller import router as config_router
from jesse.controllers.notification_controller import router as notification_router
from jesse.controllers.system_controller import router as system_router
from jesse.controllers.file_controller import router as file_router
from jesse.controllers.lsp_controller import router as lsp_router
from jesse.controllers.closed_trade_controller import router as closed_trade_router
from jesse.controllers.order_controller import router as order_router
from jesse.controllers.tabs_controller import router as tabs_router
from jesse.controllers.period_templates_controller import router as period_templates_router
from jesse.controllers.route_templates_controller import router as route_templates_router
from jesse.controllers.ai_model_controller import router as ai_model_router
from jesse.controllers.data_provider_credentials_controller import router as data_provider_credentials_router
from jesse.controllers.mcp_controller import router as mcp_router
from jesse.controllers.project_files_controller import router as project_files_router
from jesse.controllers.research_scripts_controller import router as research_scripts_router
from jesse.controllers.session_results_controller import router as session_results_router
from jesse.controllers.analysis_controller import router as analysis_router
from jesse.services.env import is_test_env

# register routers
fastapi_app.include_router(websocket_router)
fastapi_app.include_router(optimization_router)
fastapi_app.include_router(monte_carlo_router)
fastapi_app.include_router(exchange_router)
fastapi_app.include_router(backtest_router)
fastapi_app.include_router(significance_test_router)
fastapi_app.include_router(candles_router)
fastapi_app.include_router(candles_export_router)
fastapi_app.include_router(strategy_router)
fastapi_app.include_router(auth_router)
fastapi_app.include_router(config_router)
fastapi_app.include_router(notification_router)
fastapi_app.include_router(system_router)
fastapi_app.include_router(file_router)
fastapi_app.include_router(lsp_router)
fastapi_app.include_router(closed_trade_router)
fastapi_app.include_router(order_router)
fastapi_app.include_router(tabs_router)
fastapi_app.include_router(period_templates_router)
fastapi_app.include_router(route_templates_router)
fastapi_app.include_router(ai_model_router)
fastapi_app.include_router(data_provider_credentials_router)
fastapi_app.include_router(mcp_router)
fastapi_app.include_router(project_files_router)
fastapi_app.include_router(research_scripts_router)
fastapi_app.include_router(session_results_router)
fastapi_app.include_router(analysis_router)

if is_test_env():
    from jesse.controllers.e2e_controller import router as e2e_router
    fastapi_app.include_router(e2e_router)

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
