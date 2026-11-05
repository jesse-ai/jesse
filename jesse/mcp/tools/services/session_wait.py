"""
wait_for_sessions: wait on the MCP side until research sessions (backtest, optimization, Monte Carlo,
significance test) end or stall, so an agent makes one call instead of polling session by session.

The service polls Jesse's /session-results/status every few seconds. A session is settled when it
ended (finished, stopped, cancelled, terminated), is still a draft or does not exist, or has
stalled: its worker is alive but has made no progress for longer than the stall limit. A worker
that died loses its lease, and Jesse then stops its session, so that case arrives as an ended
session. Waiting never cancels anything; the agent decides.

list_runners reads the research runners (machines sharing this Jesse's database that run queued
jobs; see jesse/services/runner_queue.py), for a session that waits long with outcome "queued".
"""

import json
import time
from typing import Any, Optional

import jesse.mcp.mcp_config as mcp_config
from .project_files import REQUEST_TIMEOUT_SECONDS, _call

POLL_SECONDS = 3.0
STATUS_TIMEOUT_SECONDS = 30
DEFAULT_TIMEOUT_SECONDS = 240
# Stays below the tool-call timeouts of common MCP clients; a longer wait is a second call.
MAX_TIMEOUT_SECONDS = 540
MAX_SESSIONS = 50
DEFAULT_STALL_MINUTES = {'backtest': 10, 'optimization': 30, 'monte_carlo': 20, 'significance_test': 20}
ENDED = ('finished', 'stopped', 'cancelled', 'terminated', 'failed')
_RUN_TOOLS = {
    'backtest': 'run_backtest',
    'optimization': 'run_optimization',
    'monte_carlo': 'run_monte_carlo',
    'significance_test': 'run_significance_test',
}


def _error(message: str) -> dict:
    return {'status': 'error', 'error_type': 'invalid_request', 'message': message}


def _session_ids(value: Any) -> list:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith('['):
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                raise ValueError('session_ids is not a valid JSON array.')
        else:
            value = [part.strip() for part in text.split(',') if part.strip()]
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise ValueError('session_ids must be a non-empty list of session IDs.')
    if len(value) > MAX_SESSIONS:
        raise ValueError(f'At most {MAX_SESSIONS} session IDs per call.')
    return list(dict.fromkeys(value))


def _number(name: str, value: Any, minimum: float, maximum: Optional[float] = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{name} must be a number.')
    if value < minimum or (maximum is not None and value > maximum):
        bounds = f'between {minimum} and {maximum}' if maximum is not None else f'at least {minimum}'
        raise ValueError(f'{name} must be {bounds}.')
    return float(value)


def _judge(session: dict, stall_minutes: Optional[float]) -> dict:
    """The session as reported to the agent, with `settled` and `outcome`."""
    status = session.get('status')
    kind = session.get('session_type')
    judged = {key: session[key] for key in (
        'session_id', 'session_type', 'status', 'progress', 'progress_age_seconds', 'heartbeat_age_seconds',
        'claimed_by', 'queue', 'error',
    ) if key in session}
    if kind:
        judged['dashboard_url'] = mcp_config.dashboard_url(kind, session.get('session_id'))

    if status in ENDED:
        judged.update(settled=True, outcome='finished' if status == 'finished' else 'ended')
    elif status == 'not_found':
        judged.update(settled=True, outcome='not_found')
    elif status == 'queued':
        queue = session.get('queue') or {}
        waited = queue.get('queued_age_seconds')
        note = f"Waiting for {'runner ' + queue['target'] if queue.get('target') not in (None, 'any') else 'a runner'}"
        note += f' for {waited / 60:.0f} minutes.' if waited else '.'
        if queue.get('note'):
            note += f" {queue['note']}"
        note += ' Check list_runners if it waits long.'
        judged.update(settled=False, outcome='queued', note=note)
    elif status == 'draft':
        judged.update(settled=True, outcome='not_started',
                      note=f'Still a draft: nothing is running. Start it with {_RUN_TOOLS.get(kind, "its run tool")}.')
    elif status == 'running':
        limit = stall_minutes if stall_minutes is not None else DEFAULT_STALL_MINUTES.get(kind, 20)
        age = session.get('progress_age_seconds')
        if age is None:
            judged.update(settled=False, outcome='running',
                          note='Started by a Jesse version without heartbeats, so only its end can be detected.')
        elif age > limit * 60:
            note = (f'Alive but no progress for {age / 60:.0f} minutes (stall limit {limit:g}). Check its logs; if '
                    'it is stuck, cancel it and run it again.')
            if session.get('claimed_here') is False and session.get('claimed_by'):
                note += f' It runs on {session["claimed_by"]}: cancel it through that machine\'s Jesse.'
            judged.update(settled=True, outcome='stalled', note=note)
        else:
            judged.update(settled=False, outcome='running')
    else:
        judged.update(settled=False, outcome=status or 'unknown')
    return judged


def wait_for_sessions_service(
    session_ids: Any,
    until: str = 'all',
    timeout_seconds: Any = DEFAULT_TIMEOUT_SECONDS,
    stall_minutes: Any = None,
) -> dict:
    try:
        ids = _session_ids(session_ids)
        if until not in ('all', 'any'):
            raise ValueError('until must be "all" or "any".')
        timeout = _number('timeout_seconds', timeout_seconds, 0, MAX_TIMEOUT_SECONDS)
        stall = None if stall_minutes is None else _number('stall_minutes', stall_minutes, 1)
    except ValueError as e:
        return _error(str(e))

    started = time.monotonic()
    judged = None
    last_failure = None
    while True:
        result = _call('wait_for_sessions', '/session-results/status', {'session_ids': ids}, STATUS_TIMEOUT_SECONDS)
        if result.get('status') == 'success':
            judged = [_judge(session, stall) for session in result.get('sessions', [])]
            last_failure = None
            settled = [session['settled'] for session in judged]
            done = all(settled) if until == 'all' else any(settled)
            if done:
                break
        elif judged is None and result.get('error_type') in ('invalid_request', 'authentication_failed'):
            return result
        else:
            last_failure = result
        if time.monotonic() - started + POLL_SECONDS > timeout:
            break
        time.sleep(POLL_SECONDS)

    waited = round(time.monotonic() - started, 1)
    if judged is None:
        failure = last_failure or {}
        return {
            'status': 'error',
            'error_type': failure.get('error_type', 'connection_error'),
            'message': f"Could not read the sessions' status for {waited} seconds: {failure.get('message', '')}".strip(),
        }

    counts = {}
    for session in judged:
        counts[session['outcome']] = counts.get(session['outcome'], 0) + 1
    done = all(s['settled'] for s in judged) if until == 'all' else any(s['settled'] for s in judged)
    response = {
        'status': 'success',
        'done': done,
        'until': until,
        'waited_seconds': waited,
        'outcomes': counts,
        'sessions': judged,
    }
    if not done:
        response['next'] = 'Not done yet: call wait_for_sessions again with the same session_ids.'
    if last_failure is not None:
        response['warning'] = f"The last status read failed ({last_failure.get('message', 'unknown error')}); statuses are from the read before it."
    return response


def list_runners_service() -> dict:
    """The research runners sharing this Jesse's database (/session-results/runners)."""
    result = _call('list_runners', '/session-results/runners', {}, REQUEST_TIMEOUT_SECONDS)
    if result.get('http_status') == 404:
        result['message'] = ('This Jesse has no research runners (its version predates them), so every run '
                             'starts on it: leave `where` at its default.')
    return result
