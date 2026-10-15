"""
Jesse Session Results and Temporary Analysis Service Functions

Thin clients for the /session-results and /analysis API routes. Jesse reads the stored
sessions, writes analysis snapshots, runs analysis code, and reads artifacts on the machine
running Jesse, so these tools work the same when the assistant runs on another computer.
"""
from typing import Any, List, Optional

import jesse.mcp.mcp_config as mcp_config
from .project_files import CANCEL_TIMEOUT_SECONDS, REQUEST_TIMEOUT_SECONDS, TRANSFER_TIMEOUT_SECONDS, _call

# Result pages are bounded by the API (128 KiB of JSON), but a large Monte Carlo record is
# parsed from the database for each page, which can take several seconds.
RESULTS_TIMEOUT_SECONDS = 60


def _succeeded(result: dict) -> bool:
    return result.get('status') == 'success'


def get_session_results_service(session_type: str, session_id: str, section: str = 'summary',
                                offset: int = 0, limit: int = 50) -> dict:
    result = _call(
        'get_session_results', '/session-results/get',
        {'session_type': session_type, 'session_id': session_id, 'section': section, 'offset': offset, 'limit': limit},
        RESULTS_TIMEOUT_SECONDS,
    )
    if _succeeded(result):
        # From the type and ID the API echoes back (validated and normalized), so every summary and
        # section page of an existing session carries its link. Page budgets cover the items only.
        result['dashboard_url'] = mcp_config.dashboard_url(result.get('session_type'), result.get('session_id'))
    return result


def get_live_sessions_service(limit: int = 20, offset: int = 0, status_filter: Optional[str] = None,
                              mode_filter: Optional[str] = None, title_search: Optional[str] = None) -> dict:
    result = _call(
        'get_live_sessions', '/session-results/live-sessions',
        {'limit': limit, 'offset': offset, 'status_filter': status_filter, 'mode_filter': mode_filter,
         'title_search': title_search},
        RESULTS_TIMEOUT_SECONDS,
    )
    if _succeeded(result):
        result['sessions'] = mcp_config.with_dashboard_urls('live', result.get('sessions'))
    return result


def _with_session_link_template(result: dict) -> dict:
    """
    Add the live session link template to a history page. A page is cut to a byte budget on the
    Jesse host (live_history.MAX_RESPONSE_BYTES), so it gets this one constant-size field, which
    fits the budget's transport allowance, rather than a link per session.
    """
    if _succeeded(result):
        result['session_dashboard_url_template'] = mcp_config.dashboard_url_template('live')
    return result


def get_live_trades_service(start: Any = None, end: Any = None, recent_days: Any = None, mode: Any = 'live',
                            exchange: Any = None, symbol: Any = None, session_id: Any = None,
                            order: Any = 'newest_first', cursor: Any = None, limit: Any = 100) -> dict:
    return _with_session_link_template(_call(
        'get_live_trades', '/session-results/live-trades',
        {'start': start, 'end': end, 'recent_days': recent_days, 'mode': mode, 'exchange': exchange,
         'symbol': symbol, 'session_id': session_id, 'order': order, 'cursor': cursor, 'limit': limit},
        RESULTS_TIMEOUT_SECONDS,
    ))


def get_live_orders_service(start: Any = None, end: Any = None, recent_days: Any = None, mode: Any = 'live',
                            exchange: Any = None, symbol: Any = None, session_id: Any = None,
                            time_field: Any = 'created_at', status: Any = None, order: Any = 'newest_first',
                            cursor: Any = None, limit: Any = 100) -> dict:
    return _with_session_link_template(_call(
        'get_live_orders', '/session-results/live-orders',
        {'start': start, 'end': end, 'recent_days': recent_days, 'mode': mode, 'exchange': exchange,
         'symbol': symbol, 'session_id': session_id, 'time_field': time_field, 'status': status, 'order': order,
         'cursor': cursor, 'limit': limit},
        RESULTS_TIMEOUT_SECONDS,
    ))


def run_analysis_service(code: str, inputs: Optional[List[dict]] = None, timeout_minutes: int = 5) -> dict:
    # Writing snapshots of large sessions or history windows happens inside this request.
    return _call(
        'run_analysis', '/analysis/run',
        {'code': code, 'inputs': list(inputs or []), 'timeout_minutes': timeout_minutes},
        TRANSFER_TIMEOUT_SECONDS,
    )


def get_analysis_job_service(job_id: str = '', tail_lines: int = 50) -> dict:
    return _call('get_analysis_job', '/analysis/jobs', {'job_id': job_id, 'tail_lines': tail_lines}, REQUEST_TIMEOUT_SECONDS)


def cancel_analysis_job_service(job_id: str) -> dict:
    return _call('cancel_analysis_job', '/analysis/cancel', {'job_id': job_id}, CANCEL_TIMEOUT_SECONDS)


def delete_analysis_job_service(job_id: str) -> dict:
    return _call('delete_analysis_job', '/analysis/delete', {'job_id': job_id}, TRANSFER_TIMEOUT_SECONDS)


def get_analysis_artifact_service(job_id: str, path: str) -> dict:
    return _call('get_analysis_artifact', '/analysis/artifact', {'job_id': job_id, 'path': path}, REQUEST_TIMEOUT_SECONDS)
