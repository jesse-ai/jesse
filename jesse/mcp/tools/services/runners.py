"""
Research runners on the MCP side: the `where` argument of the run tools and the response for a
run Jesse queued for a runner instead of starting it.

A research runner is a machine sharing this Jesse's database that claims queued research jobs
(see jesse/services/runner_queue.py). A queued start answers 202 with
{"status": "queued", "session_id", "job_id", "target", "message", "warning"?}; the resume routes
answer 200 with the same fields next to "session". list_runners_service is in session_wait.py:
this module is imported by the run services, before the services package imports project_files
(which a star import of candles.py would otherwise shadow).
"""
from typing import Any, Optional

import jesse.mcp.mcp_config as mcp_config

DEFAULT_WHERE = 'auto'


def invalid_where(where: Any) -> Optional[dict]:
    """The error to return for a `where` that is not a non-empty string, else None."""
    if isinstance(where, str) and where.strip():
        return None
    return {
        'status': 'error',
        'error_type': 'invalid_request',
        'message': ('where must be "auto", "local", "any", or a runner name from list_runners '
                    '(a non-empty string).'),
    }


def normalized_where(where: str) -> str:
    return where.strip()


def response_body(response) -> dict:
    """The JSON object a Jesse response carries, or {} (no body, not JSON, or not an object)."""
    try:
        body = response.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def body_error(response) -> Optional[str]:
    """The `error` text Jesse gives with a refused start (a bad `where`, already running)."""
    error = response_body(response).get('error')
    return error if isinstance(error, str) and error else None


def with_error_details(result: dict, response) -> dict:
    """An error result with Jesse's own reason added as `details` when it gave one."""
    error = body_error(response)
    if error:
        result['details'] = error
    return result


def queued_result(session_type: str, session_id: str, body: dict) -> Optional[dict]:
    """The tool response for a run Jesse queued for a runner, or None when it started here."""
    if body.get('status') != 'queued':
        return None
    target = body.get('target') or 'any'
    where = 'any runner' if target == 'any' else f'runner {target}'
    result = {
        'status': 'queued',
        'session_id': body.get('session_id') or session_id,
        'target': target,
        'job_id': body.get('job_id'),
        'dashboard_url': mcp_config.dashboard_url(session_type, body.get('session_id') or session_id),
        'message': f'Queued for {where}. Call wait_for_sessions([session_id]) to wait for it.',
    }
    if body.get('warning'):
        result['warning'] = body['warning']
    return result


def already_queued_result(session_type: str, session_id: str, label: str) -> dict:
    """A run tool called again for a session that is still waiting for a runner."""
    return {
        'status': 'queued',
        'session_id': session_id,
        'dashboard_url': mcp_config.dashboard_url(session_type, session_id),
        'message': (f'{label} session {session_id} is already queued for a research runner. '
                    'Call wait_for_sessions([session_id]) to wait for it; do not start it again.'),
    }
