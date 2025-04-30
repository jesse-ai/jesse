from fastapi import APIRouter, Header, Query
from typing import Optional, List
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from jesse.services import auth as authenticator
from jesse.services.multiprocessing import process_manager
from jesse.services.web import OptimizationRequestJson, CancelRequestJson, UpdateOptimizationSessionStateRequestJson, UpdateOptimizationSessionStatusRequestJson, TerminateOptimizationRequestJson
from jesse import helpers as jh
from jesse.models.OptimizationSession import get_optimization_sessions as get_sessions, update_optimization_session_state, update_optimization_session_status, delete_optimization_session, reset_optimization_session
from jesse.services.transformers import get_optimization_session, get_optimization_session_for_load_more
from jesse.models.OptimizationSession import get_optimization_session_by_id as get_optimization_session_by_id_from_db
from jesse.modes.optimize_mode import run as run_optimization


router = APIRouter(prefix="/optimization", tags=["Optimization"])


@router.post("")
async def optimization(request_json: OptimizationRequestJson, authorization: Optional[str] = Header(None)):
    """
    Start an optimization process
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    jh.validate_cwd()

    # Check Python version before imports
    if jh.python_version() == (3, 13):
        return JSONResponse({
            'error': 'Optimization is not supported on Python 3.13',
            'message': 'The Ray library used for optimization does not support Python 3.13 yet. Please use Python 3.12 or lower.'
        }, status_code=500)

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
        request_json.cpu_cores,
        request_json.state,
    )

    return JSONResponse({'message': 'Started optimization...'}, status_code=202)


@router.post("/rerun")
async def rerun_optimization(request_json: OptimizationRequestJson, authorization: Optional[str] = Header(None)):
    """
    Start an optimization process
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    jh.validate_cwd()

    # Check Python version before imports
    if jh.python_version() == (3, 13):
        return JSONResponse({
            'error': 'Optimization is not supported on Python 3.13',
            'message': 'The Ray library used for optimization does not support Python 3.13 yet. Please use Python 3.12 or lower.'
        }, status_code=500)

    # Get the session from the database
    session = get_optimization_session_by_id_from_db(request_json.id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {request_json.id} not found'
        }, status_code=404)

    # reset the session
    reset_optimization_session(request_json.id)

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
        request_json.cpu_cores,
        request_json.state,
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


@router.post("/sessions")
def get_optimization_sessions(authorization: Optional[str] = Header(None)):
    """
    Get a list of all optimization sessions sorted by most recently updated
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    # Get sessions from the database
    sessions = get_sessions()

    # Transform the sessions using the transformer
    transformed_sessions = [get_optimization_session(session) for session in sessions]

    return JSONResponse({
        'sessions': transformed_sessions,
        'count': len(transformed_sessions)
    })


@router.post("/sessions/{session_id}")
def get_optimization_session_by_id(session_id: str, authorization: Optional[str] = Header(None)):
    """
    Get a single optimization session by ID
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    # Get the session from the database
    session = get_optimization_session_by_id_from_db(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    # Transform the session using the transformer
    transformed_session = get_optimization_session_for_load_more(session)

    return JSONResponse({
        'session': transformed_session
    })


@router.post("/update-state")
def update_session_state(request_json: UpdateOptimizationSessionStateRequestJson, authorization: Optional[str] = Header(None)):
    """
    Update the state of an optimization session
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    update_optimization_session_state(request_json.id, request_json.state)

    return JSONResponse({
        'message': 'Optimization session state updated successfully'
    })


@router.post("/terminate")
def terminate_optimization(request_json: TerminateOptimizationRequestJson, authorization: Optional[str] = Header(None)):
    """
    Terminate an optimization process
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    # First update the status to 'terminated'
    update_optimization_session_status(request_json.id, 'terminated')

    # Then request cancellation of the current process
    process_manager.cancel_process(request_json.id)

    return JSONResponse({'message': f'Optimization process with ID of {request_json.id} was terminated'}, status_code=202)


@router.post("/resume")
async def resume_optimization(request_json: OptimizationRequestJson, authorization: Optional[str] = Header(None)):
    """
    Resume an optimization process
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    jh.validate_cwd()

    # Check Python version before imports
    if jh.python_version() == (3, 13):
        return JSONResponse({
            'error': 'Optimization is not supported on Python 3.13',
            'message': 'The Ray library used for optimization does not support Python 3.13 yet. Please use Python 3.12 or lower.'
        }, status_code=500)

    # Get the session from the database
    session = get_optimization_session_by_id_from_db(request_json.id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {request_json.id} not found'
        }, status_code=404)

    # Transform the session using the transformer
    transformed_session = get_optimization_session_for_load_more(session)

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
        request_json.cpu_cores,
        request_json.state,
    )

    return JSONResponse({
        'session': transformed_session
    })


@router.post("/sessions/{session_id}/remove")
def remove_optimization_session(session_id: str, authorization: Optional[str] = Header(None)):
    """
    Remove an optimization session from the database
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    session = get_optimization_session_by_id_from_db(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    # Delete the session from the database
    result = delete_optimization_session(session_id)

    if not result:
        return JSONResponse({
            'error': f'Failed to delete session with ID {session_id}'
        }, status_code=500)

    return JSONResponse({
        'message': 'Optimization session removed successfully'
    })
