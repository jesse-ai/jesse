from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, FileResponse

from jesse.services.auth import require_auth, require_auth_any
from jesse.services.multiprocessing import process_manager
from jesse.services.web import (
    SignificanceTestRequestJson,
    CancelSignificanceTestRequestJson,
    TerminateSignificanceTestRequestJson,
    UpdateSignificanceTestSessionStateRequestJson,
    UpdateSignificanceTestSessionNotesRequestJson,
    GetSignificanceTestSessionsRequestJson,
)
from jesse import helpers as jh
from jesse.models.SignificanceTestSession import (
    get_significance_test_session_by_id,
    get_significance_test_sessions,
    store_significance_test_session,
    update_significance_test_session_status,
    update_significance_test_session_state,
    update_significance_test_session_notes,
    delete_significance_test_session,
    purge_significance_test_sessions,
    get_running_significance_test_session_id,
)
from jesse.services.transformers import (
    get_significance_test_session,
    get_significance_test_session_for_load_more,
)
from jesse.modes.significance_test_mode import run as run_significance_test

router = APIRouter(prefix="/significance-test", tags=["Significance Test"])


@router.post("", dependencies=[Depends(require_auth)])
async def significance_test(
    request_json: SignificanceTestRequestJson,
):

    jh.validate_cwd()

    if not request_json.routes or len(request_json.routes) == 0:
        return JSONResponse({'error': 'Exactly one trading route is required.'}, status_code=400)

    if len(request_json.routes) != 1:
        return JSONResponse({'error': 'Rule Significance Test requires exactly one trading route.'}, status_code=400)

    session_id = request_json.id or jh.generate_unique_id()

    existing = get_significance_test_session_by_id(session_id)
    if existing and existing.status != 'draft':
        return JSONResponse(
            {'error': f'Session {session_id} already exists.'},
            status_code=409,
        )

    if existing:
        # Reuse a pre-staged draft (created via /significance-test/update-state by
        # the dashboard, MCP, or other clients). Promote it to 'running' and refresh
        # state/theme with whatever the start request carries.
        update_significance_test_session_state(session_id, request_json.state)
        update_significance_test_session_status(session_id, 'running')
        if request_json.theme:
            from jesse.models.SignificanceTestSession import SignificanceTestSession
            SignificanceTestSession.update(theme=request_json.theme).where(
                SignificanceTestSession.id == session_id
            ).execute()
    else:
        # Create the session record immediately so the frontend can find it while
        # candles are still loading in the background process
        store_significance_test_session(
            id=session_id,
            status='running',
            state=request_json.state,
            theme=request_json.theme,
        )

    process_manager.add_task(
        run_significance_test,
        session_id,
        request_json.config,
        request_json.exchange,
        request_json.routes,
        request_json.data_routes,
        request_json.start_date,
        request_json.finish_date,
        request_json.n_simulations,
        request_json.random_seed,
        request_json.theme,
        request_json.state,
    )

    return JSONResponse({
        'message': 'Started Rule Significance Test...',
        'session_id': session_id,
    }, status_code=202)


@router.post("/cancel", dependencies=[Depends(require_auth)])
def cancel_significance_test(
    request_json: CancelSignificanceTestRequestJson,
):

    process_manager.cancel_process(request_json.id)
    return JSONResponse(
        {'message': f'Significance Test process {request_json.id} was requested for termination'},
        status_code=202,
    )


@router.post("/terminate", dependencies=[Depends(require_auth)])
def terminate_significance_test(
    request_json: TerminateSignificanceTestRequestJson,
):

    update_significance_test_session_status(request_json.id, 'terminated')
    process_manager.cancel_process(request_json.id)
    return JSONResponse(
        {'message': f'Significance Test process {request_json.id} was terminated'},
        status_code=202,
    )


@router.post("/update-state", dependencies=[Depends(require_auth)])
def update_state(
    request_json: UpdateSignificanceTestSessionStateRequestJson,
):

    update_significance_test_session_state(request_json.id, request_json.state)
    return JSONResponse({'message': 'Session state updated successfully'})


@router.post("/sessions", dependencies=[Depends(require_auth)])
def list_sessions(
    request_json: GetSignificanceTestSessionsRequestJson = GetSignificanceTestSessionsRequestJson(),
):

    sessions = get_significance_test_sessions(
        limit=request_json.limit,
        offset=request_json.offset,
        title_search=request_json.title_search,
        status_filter=request_json.status_filter,
        date_filter=request_json.date_filter,
    )
    transformed = [get_significance_test_session(s) for s in sessions]
    return JSONResponse({'sessions': transformed, 'count': len(transformed)})


@router.post("/sessions/{session_id}", dependencies=[Depends(require_auth)])
def get_session(session_id: str):

    session = get_significance_test_session_by_id(session_id)
    if not session:
        return JSONResponse({'error': f'Session {session_id} not found'}, status_code=404)

    transformed = get_significance_test_session_for_load_more(session)
    transformed = jh.clean_infinite_values(transformed)
    return JSONResponse({'session': transformed})


@router.get("/sessions/{session_id}/chart", dependencies=[Depends(require_auth_any)])
def get_chart(session_id: str):
    session = get_significance_test_session_by_id(session_id)
    if not session:
        return JSONResponse({'error': f'Session {session_id} not found'}, status_code=404)
    if not session.chart_path:
        return JSONResponse({'error': 'Chart not yet available'}, status_code=404)

    import os
    if not os.path.exists(session.chart_path):
        return JSONResponse({'error': 'Chart file not found on disk'}, status_code=404)

    return FileResponse(session.chart_path, media_type='image/png')


@router.post("/sessions/{session_id}/remove", dependencies=[Depends(require_auth)])
def remove_session(session_id: str):

    session = get_significance_test_session_by_id(session_id)
    if not session:
        return JSONResponse({'error': f'Session {session_id} not found'}, status_code=404)

    result = delete_significance_test_session(session_id)
    if not result:
        return JSONResponse({'error': 'Failed to delete session'}, status_code=500)

    return JSONResponse({'message': 'Session removed successfully'})


@router.post("/sessions/{session_id}/notes", dependencies=[Depends(require_auth)])
def update_notes(
    session_id: str,
    request_json: UpdateSignificanceTestSessionNotesRequestJson,
):

    session = get_significance_test_session_by_id(session_id)
    if not session:
        return JSONResponse({'error': f'Session {session_id} not found'}, status_code=404)

    update_significance_test_session_notes(
        session_id,
        title=request_json.title,
        description=request_json.description,
        strategy_codes=request_json.strategy_codes,
    )
    return JSONResponse({'message': 'Notes updated successfully'})


@router.post("/sessions/{session_id}/strategy-code", dependencies=[Depends(require_auth)])
def get_strategy_code(session_id: str):

    import json
    session = get_significance_test_session_by_id(session_id)
    if not session:
        return JSONResponse({'error': f'Session {session_id} not found'}, status_code=404)

    return JSONResponse({
        'strategy_code': json.loads(session.strategy_codes) if session.strategy_codes else {}
    })



@router.post("/purge-sessions", dependencies=[Depends(require_auth)])
def purge_sessions(request_json: dict):

    days_old = request_json.get('days_old', None)
    deleted_count = purge_significance_test_sessions(days_old)
    return JSONResponse({
        'message': f'Successfully purged {deleted_count} session(s)',
        'deleted_count': deleted_count,
    })


@router.get("/running-session", dependencies=[Depends(require_auth)])
def get_running_session():

    return JSONResponse({'session_id': get_running_significance_test_session_id()})
