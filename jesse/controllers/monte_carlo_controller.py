from fastapi import APIRouter, Header, Request
from typing import Optional
from fastapi.responses import JSONResponse
import json

from jesse.services import auth as authenticator
from jesse.services.multiprocessing import process_manager
from jesse.services.web import (
    MonteCarloRequestJson,
    CancelMonteCarloRequestJson,
    UpdateMonteCarloSessionStateRequestJson,
    TerminateMonteCarloRequestJson,
    UpdateMonteCarloSessionNotesRequestJson,
    GetMonteCarloSessionsRequestJson
)
from jesse import helpers as jh
from jesse.models.MonteCarloSession import (
    get_monte_carlo_sessions,
    update_monte_carlo_session_state,
    update_monte_carlo_session_status,
    delete_monte_carlo_session,
    get_monte_carlo_session_by_id,
    update_monte_carlo_session_notes,
    purge_monte_carlo_sessions
)
from jesse.services.transformers import get_monte_carlo_session, get_monte_carlo_session_for_load_more
from jesse.modes.monte_carlo_mode import run as run_monte_carlo


router = APIRouter(prefix="/monte-carlo", tags=["Monte Carlo"])


@router.post("")
async def monte_carlo(request: Request, request_json: MonteCarloRequestJson, authorization: Optional[str] = Header(None)):
    """
    Start a Monte Carlo simulation
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    jh.validate_cwd()

    # Check Python version before imports
    if jh.python_version() == (3, 13):
        return JSONResponse({
            'error': 'Monte Carlo mode is not supported on Python 3.13',
            'message': 'The Ray library used for Monte Carlo does not support Python 3.13 yet. Please use Python 3.12 or lower.'
        }, status_code=500)

    # Validate at least one type is selected
    if not request_json.run_trades and not request_json.run_candles:
        return JSONResponse({
            'error': 'At least one Monte Carlo type must be selected',
            'message': 'Please select either Trades, Candles, or both.'
        }, status_code=400)

    # Validate routes
    if not request_json.routes or len(request_json.routes) == 0:
        return JSONResponse({
            'error': 'At least one route is required',
            'message': 'Please add at least one trading route.'
        }, status_code=400)

    # Generate unique session ID if not provided
    session_id = request_json.id or jh.generate_unique_id()
    
    

    # Check if session already exists
    existing_session = get_monte_carlo_session_by_id(session_id)
    if existing_session:
        return JSONResponse({
            'error': f'Monte Carlo session with ID {session_id} already exists',
            'message': 'A session with this ID is already running or completed.'
        }, status_code=409)

    # Check session existence in monte carlo models
    from jesse.models.MonteCarloSession import get_monte_carlo_session_by_id as db_get_mc_session_by_id
    if db_get_mc_session_by_id(session_id):
        return JSONResponse({
            'error': f'Monte Carlo session with ID {session_id} already exists (in DB)',
            'message': 'A session with this ID already exists in the database.'
        }, status_code=409)
    process_manager.add_task(
        run_monte_carlo,
        session_id,
        request_json.config,
        request_json.exchange,
        request_json.routes,
        request_json.data_routes,
        request_json.start_date,
        request_json.finish_date,
        request_json.run_trades,
        request_json.run_candles,
        request_json.num_scenarios,
        request_json.fast_mode,
        request_json.cpu_cores,
        request_json.pipeline_type,
        request_json.pipeline_params,
        request_json.state,
    )

    return JSONResponse({
        'message': 'Started Monte Carlo simulation...',
        'session_id': session_id
    }, status_code=202)


@router.post("/cancel")
def cancel_monte_carlo(request_json: CancelMonteCarloRequestJson, authorization: Optional[str] = Header(None)):
    """
    Cancel a Monte Carlo simulation
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    process_manager.cancel_process(request_json.id)

    return JSONResponse(
        {'message': f'Monte Carlo process with ID of {request_json.id} was requested for termination'},
        status_code=202
    )


@router.post("/terminate")
def terminate_monte_carlo(request_json: TerminateMonteCarloRequestJson, authorization: Optional[str] = Header(None)):
    """
    Terminate a Monte Carlo simulation
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    # First update the status to 'terminated'
    update_monte_carlo_session_status(request_json.id, 'terminated')

    # Then request cancellation of the current process
    process_manager.cancel_process(request_json.id)

    return JSONResponse(
        {'message': f'Monte Carlo process with ID of {request_json.id} was terminated'},
        status_code=202
    )


@router.post("/resume")
async def resume_monte_carlo(request_json: MonteCarloRequestJson, authorization: Optional[str] = Header(None)):
    """
    Resume a Monte Carlo simulation
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    jh.validate_cwd()

    # Check Python version
    if jh.python_version() == (3, 13):
        return JSONResponse({
            'error': 'Monte Carlo mode is not supported on Python 3.13',
            'message': 'The Ray library used for Monte Carlo does not support Python 3.13 yet. Please use Python 3.12 or lower.'
        }, status_code=500)

    # Get the session from the database
    session = get_monte_carlo_session_by_id(request_json.id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {request_json.id} not found'
        }, status_code=404)

    # Transform the session using the transformer
    transformed_session = get_monte_carlo_session_for_load_more(session)

    process_manager.add_task(
        run_monte_carlo,
        request_json.id,
        request_json.config,
        request_json.exchange,
        request_json.routes,
        request_json.data_routes,
        request_json.start_date,
        request_json.finish_date,
        request_json.run_trades,
        request_json.run_candles,
        request_json.num_scenarios,
        request_json.fast_mode,
        request_json.cpu_cores,
        request_json.pipeline_type,
        request_json.pipeline_params,
        request_json.state,
    )

    return JSONResponse({
        'session': transformed_session
    })


@router.post("/sessions")
def get_monte_carlo_sessions_endpoint(request_json: GetMonteCarloSessionsRequestJson = GetMonteCarloSessionsRequestJson(), authorization: Optional[str] = Header(None)):
    """
    Get a list of Monte Carlo sessions sorted by most recently updated with pagination and filters
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    # Get sessions from the database with pagination and filters
    sessions = get_monte_carlo_sessions(
        limit=request_json.limit,
        offset=request_json.offset,
        title_search=request_json.title_search,
        status_filter=request_json.status_filter,
        date_filter=request_json.date_filter
    )

    # Transform the sessions using the transformer
    transformed_sessions = [get_monte_carlo_session(session) for session in sessions]

    return JSONResponse({
        'sessions': transformed_sessions,
        'count': len(transformed_sessions)
    })


@router.post("/sessions/{session_id}")
def get_monte_carlo_session_by_id_endpoint(session_id: str, authorization: Optional[str] = Header(None)):
    """
    Get a single Monte Carlo session by ID
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    # Get the session from the database
    session = get_monte_carlo_session_by_id(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    # Transform the session using the transformer
    transformed_session = get_monte_carlo_session_for_load_more(session)
    # Ensure JSON-safe values (replace NaN/Inf with None)
    transformed_session = jh.clean_infinite_values(transformed_session)

    return JSONResponse({
        'session': transformed_session
    })


@router.post("/sessions/{session_id}/equity-curves")
def get_monte_carlo_equity_curves(session_id: str, authorization: Optional[str] = Header(None)):
    """
    Get equity curve data for a Monte Carlo session
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    session = get_monte_carlo_session_by_id(session_id)
    
    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)
    
    trades_equity_curves = None
    candles_equity_curves = None
    
    # Extract trades equity curves
    if session.trades_session and session.trades_session.results:
        results = jh.clean_infinite_values(json.loads(session.trades_session.results))
        
        # Extract original equity curve
        original_curve = None
        if results.get('original') and results['original'].get('equity_curve'):
            for curve in results['original']['equity_curve']:
                if curve.get('name') == 'Portfolio':
                    original_curve = curve
                    break
        
        # Extract all scenario equity curves
        scenario_curves = []
        if results.get('scenarios'):
            for scenario in results['scenarios']:
                if scenario.get('equity_curve'):
                    for curve in scenario['equity_curve']:
                        if curve.get('name') == 'Portfolio':
                            scenario_curves.append(curve)
                            break
        
        trades_equity_curves = {
            'original': original_curve,
            'scenarios': scenario_curves
        }
    
    # Extract candles equity curves
    if session.candles_session and session.candles_session.results:
        results = jh.clean_infinite_values(json.loads(session.candles_session.results))
        
        # Extract original equity curve
        original_curve = None
        if results.get('original') and results['original'].get('equity_curve'):
            for curve in results['original']['equity_curve']:
                if curve.get('name') == 'Portfolio':
                    original_curve = curve
                    break
        
        # Extract all scenario equity curves
        scenario_curves = []
        if results.get('scenarios'):
            for scenario in results['scenarios']:
                if scenario.get('equity_curve'):
                    for curve in scenario['equity_curve']:
                        if curve.get('name') == 'Portfolio':
                            scenario_curves.append(curve)
                            break
        
        candles_equity_curves = {
            'original': original_curve,
            'scenarios': scenario_curves
        }
    
    return JSONResponse({
        'trades': trades_equity_curves,
        'candles': candles_equity_curves
    })


@router.post("/update-state")
def update_session_state(
    request_json: UpdateMonteCarloSessionStateRequestJson,
    authorization: Optional[str] = Header(None)
):
    """
    Update the state of a Monte Carlo session
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    update_monte_carlo_session_state(request_json.id, request_json.state)

    return JSONResponse({
        'message': 'Monte Carlo session state updated successfully'
    })


@router.post("/sessions/{session_id}/remove")
def remove_monte_carlo_session(session_id: str, authorization: Optional[str] = Header(None)):
    """
    Remove a Monte Carlo session from the database
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    session = get_monte_carlo_session_by_id(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    # Delete the session from the database
    result = delete_monte_carlo_session(session_id)

    if not result:
        return JSONResponse({
            'error': f'Failed to delete session with ID {session_id}'
        }, status_code=500)

    return JSONResponse({
        'message': 'Monte Carlo session removed successfully'
    })


@router.post("/sessions/{session_id}/notes")
def update_session_notes(session_id: str, request_json: UpdateMonteCarloSessionNotesRequestJson, authorization: Optional[str] = Header(None)):
    """
    Update the notes (title, description, strategy_codes) of a Monte Carlo session
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    session = get_monte_carlo_session_by_id(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    update_monte_carlo_session_notes(session_id, request_json.title, request_json.description, request_json.strategy_codes)

    return JSONResponse({
        'message': 'Monte Carlo session notes updated successfully'
    })


@router.post("/sessions/{session_id}/strategy-code")
def get_session_strategy_code(session_id: str, authorization: Optional[str] = Header(None)):
    """
    Get the strategy code for a Monte Carlo session
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()
    
    session = get_monte_carlo_session_by_id(session_id)
    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)
    
    return JSONResponse({
        'strategy_code': json.loads(session.strategy_codes) if session.strategy_codes else {}
    })


@router.post("/sessions/{session_id}/logs")
def get_session_logs(session_id: str, authorization: Optional[str] = Header(None)):
    """
    Get the logs for a Monte Carlo session
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()
        
    from jesse.modes import data_provider

    content = data_provider.get_monte_carlo_logs(session_id)
    
    if content is None:
        return JSONResponse({
            'error': 'Log file not found'
        }, status_code=404)
    
    return JSONResponse({
        'logs': content
    })
    
    
@router.post("/purge-sessions")
def purge_sessions(request_json: dict, authorization: Optional[str] = Header(None)):
    """
    Purge Monte Carlo sessions older than specified days
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()
    
    days_old = request_json.get('days_old', None)
    
    deleted_count = purge_monte_carlo_sessions(days_old)
    
    return JSONResponse({
        'message': f'Successfully purged {deleted_count} session(s)',
        'deleted_count': deleted_count
    }, status_code=200)


