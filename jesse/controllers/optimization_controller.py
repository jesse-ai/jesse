from fastapi import APIRouter, Header, Query
from typing import Optional
from fastapi.responses import JSONResponse, FileResponse

from jesse.services import auth as authenticator
from jesse.services.multiprocessing import process_manager
from jesse.services.web import OptimizationRequestJson, CancelRequestJson
from jesse import helpers as jh
router = APIRouter(prefix="/optimization", tags=["Optimization"])


@router.post("")
async def optimization(request_json: OptimizationRequestJson, authorization: Optional[str] = Header(None)):
    """
    Start an optimization process
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    jh.validate_cwd()

    from jesse.modes.optimize_mode import run as run_optimization

    process_manager.add_task(
        run_optimization,
        request_json.id,
        request_json.config,
        request_json.exchange,
        request_json.routes,
        request_json.data_routes,
        request_json.training_start_date,
        request_json.training_finish_date,
        request_json.testing_start_date,
        request_json.testing_finish_date,
        request_json.optimal_total,
        request_json.fast_mode,
        request_json.cpu_cores
    )

    return JSONResponse({'message': 'Started optimization...'}, status_code=202)


@router.post("/cancel")
def cancel_optimization(request_json: CancelRequestJson, authorization: Optional[str] = Header(None)):
    """
    Cancel an optimization process
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    process_manager.cancel_process(request_json.id)

    return JSONResponse({'message': f'Optimization process with ID of {request_json.id} was requested for termination'},
                       status_code=202)


@router.get("/download-log")
def download_optimization_log(token: str = Query(...)):
    """
    Download optimization log file
    """
    if not authenticator.is_valid_token(token):
        return authenticator.unauthorized_response()

    from jesse.modes import data_provider

    return data_provider.download_file('optimize', 'log')
