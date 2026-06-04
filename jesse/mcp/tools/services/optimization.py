"""
Jesse Optimization Service Functions

Mirrors the Monte Carlo service module so the MCP agent can stage and run
hyperparameter optimizations with the same draft / run / poll workflow it
already knows for backtests, RST, and Monte Carlo.

Optimization differs from Monte Carlo in a few important ways:
  - It uses a TRAIN/TEST split (four dates) instead of a single window, so the
    optimizer tunes on the training window and reports out-of-sample metrics on
    the testing window.
  - objective_function, trials, and best_candidates_count are NOT top-level
    request fields — the optimize mode's set_config() reads them off the `config`
    dict, so they are folded into the config we send.
  - The strategy MUST declare hyperparameters() (a non-empty list) or there is
    nothing to optimize.
  - `trials` is PER hyperparameter: total trials = n_hyperparameters * trials.
  - Results are ranked best trials (params + train/test metrics), not an equity
    distribution.

Endpoints used (all under /optimization):
    POST /update-state                 create or update a draft
    POST /sessions/{id}                retrieve one session
    POST /sessions                     list sessions
    POST /sessions/{id}/notes          update notes / strategy code
    POST /sessions/{id}/logs           log file content
    POST /resume                       start an existing draft session
    POST /rerun                        reset + restart a finished/stopped session
    POST /cancel                       cooperative cancel
    POST /terminate                    force-terminate
    POST /purge-sessions               delete old sessions
"""

import json
import os
import uuid
import requests
from multiprocessing import cpu_count
from typing import Optional

import jesse.mcp.mcp_config as mcp_config
from .auth import hash_password


def _default_cpu_cores() -> int:
    try:
        return max(1, min(cpu_count() - 1, 4))
    except Exception:
        return 2


def _default_optimize_config(
    exchange_name: Optional[str],
    objective_function: str = 'sharpe',
    trials: int = 200,
    best_candidates_count: int = 20,
    warm_up_candles: int = 210,
) -> dict:
    """
    Build the config payload the optimize runner expects.

    The optimize mode's set_config() reads `objective_function`, `warm_up_candles`,
    `trials`, and `best_candidates_count` off this dict (warm_up_candles and trials
    are read unconditionally, so they must always be present). The Optimizer also
    reads `config['exchange']['type'|'futures_leverage'|'futures_leverage_mode']`
    unconditionally, so those exchange keys must always be present too (even for a
    spot exchange) to avoid a KeyError inside the spawned worker.
    """
    name = (exchange_name or '').lower()
    is_spot = 'spot' in name
    exchange = {
        'balance': 10_000,
        'fee': 0.0006,
        'type': 'spot' if is_spot else 'futures',
        # Always present — Optimize.py indexes these regardless of exchange type.
        'futures_leverage': 1,
        'futures_leverage_mode': 'cross',
    }
    return {
        'warm_up_candles': int(warm_up_candles),
        'trials': int(trials),
        'objective_function': objective_function or 'sharpe',
        'best_candidates_count': int(best_candidates_count),
        'exchange': exchange,
    }


def _build_default_title(routes_list: list) -> str:
    if routes_list:
        first = routes_list[0]
        if isinstance(first, dict):
            symbol = first.get('symbol') or 'Unknown Symbol'
            timeframe = first.get('timeframe') or 'Unknown Timeframe'
            strategy = first.get('strategy') or 'Unknown Strategy'
            suffix = f" +{len(routes_list) - 1}" if len(routes_list) > 1 else ""
            return f"MCP Optimization: {strategy} on {symbol} {timeframe}{suffix}"
    return "MCP Optimization"


def _normalize_title(title: str) -> str:
    title = title.strip() if title else "MCP Optimization"
    lowered = title.lower()
    if "mcp" in lowered and "optim" in lowered:
        return title
    return f"MCP Optimization: {title}"


def _build_default_description(
    exchange: str,
    routes_list: list,
    training_start_date: str,
    training_finish_date: str,
    testing_start_date: str,
    testing_finish_date: str,
    objective_function: str,
    trials: int,
    strategy_summary: Optional[str],
    hypothesis: Optional[str],
    rationale: Optional[str],
) -> str:
    first = routes_list[0] if routes_list else {}
    strategy_default = (
        f"`{first.get('strategy', 'Unknown')}` on `{first.get('symbol', 'unknown')}` "
        f"using the `{first.get('timeframe', 'unknown')}` timeframe."
    )
    summary_lines = [
        f"- **Strategy:** {strategy_summary or strategy_default}",
    ]
    if hypothesis:
        summary_lines.append(f"- **Hypothesis:** {hypothesis}")
    if rationale:
        summary_lines.append(f"- **Rationale:** {rationale}")
    summary_lines.extend([
        f"- **Training window:** `{training_start_date}` to `{training_finish_date}`",
        f"- **Testing window:** `{testing_start_date}` to `{testing_finish_date}`",
        f"- **Exchange:** `{exchange}`",
        f"- **Objective:** `{objective_function}`",
        f"- **Trials per hyperparameter:** {trials}",
    ])
    return (
        "## MCP Optimization Notes\n\n"
        "Generated by **Jesse MCP**.\n\n"
        "### Summary\n\n"
        + "\n".join(summary_lines)
    )


def _collect_strategy_codes(routes_list: list) -> dict:
    strategy_codes = {}
    for route in routes_list:
        if not isinstance(route, dict):
            continue
        exchange = route.get('exchange')
        symbol = route.get('symbol')
        strategy = route.get('strategy')
        if not exchange or not symbol or not strategy:
            continue
        key = f"{exchange}-{symbol}"
        if key in strategy_codes:
            continue
        path = os.path.join('strategies', strategy, '__init__.py')
        try:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    strategy_codes[key] = f.read()
        except Exception:
            pass
    return strategy_codes


def _post_notes(api_url: str, auth: str, session_id: str, title: Optional[str],
                description: Optional[str], strategy_codes: Optional[dict]) -> dict:
    payload = {
        'id': session_id,
        'title': title,
        'description': description,
        'strategy_codes': strategy_codes,
    }
    response = requests.post(
        f'{api_url}/optimization/sessions/{session_id}/notes',
        json=payload,
        headers={'Authorization': auth},
        timeout=10,
    )
    if response.status_code == 200:
        return {'status': 'success', 'message': 'Notes updated'}
    if response.status_code == 401:
        return {'status': 'error', 'message': 'Authentication failed'}
    if response.status_code == 404:
        return {'status': 'error', 'message': f'Session {session_id} not found'}
    return {'status': 'error', 'message': f'Failed to update notes: {response.text}'}


def create_optimization_draft_service(
    exchange: str = "Binance Perpetual Futures",
    routes: str = '[{"exchange": "Binance Perpetual Futures", "strategy": "ExampleStrategy", "symbol": "BTC-USDT", "timeframe": "4h"}]',
    data_routes: str = '[]',
    training_start_date: str = "2021-01-01",
    training_finish_date: str = "2022-06-01",
    testing_start_date: str = "2022-06-01",
    testing_finish_date: str = "2023-01-01",
    optimal_total: int = 50,
    objective_function: str = "sharpe",
    trials: int = 200,
    best_candidates_count: int = 20,
    warm_up_candles: int = 210,
    fast_mode: bool = True,
    cpu_cores: Optional[int] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    strategy_summary: Optional[str] = None,
    hypothesis: Optional[str] = None,
    rationale: Optional[str] = None,
) -> dict:
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth = hash_password(password)
        session_id = str(uuid.uuid4())

        try:
            routes_list = json.loads(routes)
            data_routes_list = json.loads(data_routes)
        except json.JSONDecodeError as e:
            return {'status': 'error', 'message': 'Invalid JSON for routes/data_routes', 'details': str(e)}

        if not isinstance(routes_list, list) or not isinstance(data_routes_list, list):
            return {'status': 'error', 'message': 'routes and data_routes must be JSON arrays'}

        if not routes_list:
            return {'status': 'error', 'message': 'At least one trading route is required.'}

        if objective_function and objective_function.lower() not in (
            'sharpe', 'calmar', 'sortino', 'omega', 'serenity', 'smart sharpe', 'smart sortino'
        ):
            return {'status': 'error',
                    'message': f'Unsupported objective_function "{objective_function}". '
                               'Use one of: sharpe, calmar, sortino, omega, serenity, smart sharpe, smart sortino.'}

        # The form stores both the run parameters and the optimization knobs
        # (objective_function/trials/best_candidates_count/warm_up_candles) so the
        # run step can rebuild the config dict without a separate config store.
        form_data = {
            'id': session_id,
            'exchange': exchange,
            'routes': routes_list,
            'data_routes': data_routes_list,
            'training_start_date': training_start_date,
            'training_finish_date': training_finish_date,
            'testing_start_date': testing_start_date,
            'testing_finish_date': testing_finish_date,
            'optimal_total': int(optimal_total),
            'fast_mode': bool(fast_mode),
            'cpu_cores': int(cpu_cores) if cpu_cores is not None else _default_cpu_cores(),
            'objective_function': objective_function or 'sharpe',
            'trials': int(trials),
            'best_candidates_count': int(best_candidates_count),
            'warm_up_candles': int(warm_up_candles),
        }

        state_dict = {
            'form': form_data,
            'results': {
                'alert': {'message': '', 'type': ''},
            },
        }

        response = requests.post(
            f'{api_url}/optimization/update-state',
            json={'id': session_id, 'state': state_dict},
            headers={'Authorization': auth},
            timeout=10,
        )

        if response.status_code == 401:
            return {'status': 'error', 'message': 'Authentication failed'}
        if response.status_code != 200:
            return {'status': 'error', 'message': f'Failed to persist draft: {response.text}'}

        note_title = _normalize_title(title or _build_default_title(routes_list))
        note_description = description or _build_default_description(
            exchange=exchange,
            routes_list=routes_list,
            training_start_date=training_start_date,
            training_finish_date=training_finish_date,
            testing_start_date=testing_start_date,
            testing_finish_date=testing_finish_date,
            objective_function=objective_function or 'sharpe',
            trials=int(trials),
            strategy_summary=strategy_summary,
            hypothesis=hypothesis,
            rationale=rationale,
        )
        strategy_codes = _collect_strategy_codes(routes_list)
        notes_result = _post_notes(
            api_url=api_url,
            auth=auth,
            session_id=session_id,
            title=note_title,
            description=note_description,
            strategy_codes=strategy_codes or None,
        )

        result = {
            'status': 'success',
            'session_id': session_id,
            'draft_state': state_dict,
            'notes': {
                'title': note_title,
                'description': note_description,
                'strategy_code_keys': list(strategy_codes.keys()),
                'strategy_codes_captured': len(strategy_codes),
            },
            'dashboard_url': mcp_config.dashboard_url('optimization', session_id),
            'message': f'Optimization draft created with ID: {session_id}',
        }
        if notes_result.get('status') != 'success':
            result['warning'] = notes_result.get('message')
        return result

    except requests.exceptions.RequestException as e:
        return {'status': 'error', 'error': str(e), 'message': 'Failed to connect to Jesse API'}
    except Exception as e:
        return {'status': 'error', 'error': str(e), 'message': 'Failed to create optimization draft'}


def update_optimization_draft_service(session_id: str, state: str) -> dict:
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth = hash_password(password)
        state_dict = json.loads(state)

        response = requests.post(
            f'{api_url}/optimization/update-state',
            json={'id': session_id, 'state': state_dict},
            headers={'Authorization': auth},
            timeout=10,
        )

        if response.status_code == 200:
            return {
                'status': 'success',
                'session_id': session_id,
                'draft_state': state_dict,
                'message': 'Optimization draft updated successfully',
            }
        if response.status_code == 401:
            return {'status': 'error', 'message': 'Authentication failed'}
        return {'status': 'error', 'message': f'Failed to update draft: {response.text}'}

    except json.JSONDecodeError as e:
        return {'status': 'error', 'error': 'Invalid JSON format', 'details': str(e),
                'message': 'Failed to parse state JSON'}
    except requests.exceptions.RequestException as e:
        return {'status': 'error', 'error': str(e), 'message': 'Failed to connect to Jesse API'}
    except Exception as e:
        return {'status': 'error', 'error': str(e), 'message': 'Failed to update optimization draft'}


def update_optimization_notes_service(
    session_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    strategy_codes: Optional[str] = None,
) -> dict:
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth = hash_password(password)
        parsed_codes = None
        if strategy_codes is not None:
            parsed_codes = json.loads(strategy_codes)
            if not isinstance(parsed_codes, dict):
                return {'status': 'error', 'message': 'strategy_codes must be a JSON object string'}

        result = _post_notes(api_url, auth, session_id, title, description, parsed_codes)
        if result.get('status') == 'success':
            return {
                'status': 'success',
                'session_id': session_id,
                'title': title,
                'description': description,
                'strategy_code_keys': list(parsed_codes.keys()) if parsed_codes else [],
                'strategy_codes_captured': len(parsed_codes) if parsed_codes else 0,
                'message': 'Optimization session notes updated successfully',
            }
        return result

    except json.JSONDecodeError as e:
        return {'status': 'error', 'error': 'Invalid JSON format', 'details': str(e),
                'message': 'Failed to parse strategy_codes JSON'}
    except requests.exceptions.RequestException as e:
        return {'status': 'error', 'error': str(e), 'message': 'Failed to connect to Jesse API'}
    except Exception as e:
        return {'status': 'error', 'error': str(e), 'message': 'Failed to update optimization notes'}


def get_optimization_session_service(session_id: str) -> dict:
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth = hash_password(password)
        response = requests.post(
            f'{api_url}/optimization/sessions/{session_id}',
            headers={'Authorization': auth},
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            return {
                'data': {'session': data.get('session', {})},
                'dashboard_url': mcp_config.dashboard_url('optimization', session_id),
                'error': None,
                'message': 'Optimization session retrieved successfully',
            }
        if response.status_code == 404:
            return {'data': None, 'error': f'Session {session_id} not found',
                    'message': f'Session {session_id} not found'}
        if response.status_code == 401:
            return {'data': None, 'error': 'Authentication failed', 'message': 'Authentication failed'}
        return {'data': None, 'error': f'Failed to retrieve session: {response.text}',
                'message': f'Failed to retrieve session: {response.text}'}

    except requests.exceptions.RequestException as e:
        return {'data': None, 'error': f'Failed to connect to Jesse API: {str(e)}',
                'message': f'Failed to connect to Jesse API: {str(e)}'}
    except Exception as e:
        return {'data': None, 'error': f'Failed to retrieve session: {str(e)}',
                'message': f'Failed to retrieve session: {str(e)}'}


def get_optimization_sessions_service(
    limit: int = 50,
    offset: int = 0,
    title_search: Optional[str] = None,
    status_filter: Optional[str] = None,
    date_filter: Optional[str] = None,
) -> dict:
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth = hash_password(password)
        payload = {
            'limit': int(limit),
            'offset': int(offset),
            'title_search': title_search,
            'status_filter': status_filter,
            'date_filter': date_filter,
        }
        response = requests.post(
            f'{api_url}/optimization/sessions',
            json=payload,
            headers={'Authorization': auth},
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            return {
                'status': 'success',
                'sessions': data.get('sessions', []),
                'count': data.get('count', 0),
                'message': f'Retrieved {data.get("count", 0)} optimization session(s)',
            }
        if response.status_code == 401:
            return {'status': 'error', 'message': 'Authentication failed'}
        return {'status': 'error', 'message': f'Failed to retrieve sessions: {response.text}'}

    except requests.exceptions.RequestException as e:
        return {'status': 'error', 'error': str(e), 'message': 'Failed to connect to Jesse API'}
    except Exception as e:
        return {'status': 'error', 'error': str(e), 'message': 'Failed to retrieve optimization sessions'}


def get_optimization_logs_service(session_id: str) -> dict:
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth = hash_password(password)
        response = requests.post(
            f'{api_url}/optimization/sessions/{session_id}/logs',
            headers={'Authorization': auth},
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            return {
                'status': 'success',
                'session_id': session_id,
                'logs': data.get('logs', ''),
                'message': 'Logs retrieved successfully',
            }
        if response.status_code == 404:
            return {'status': 'error', 'message': f'Log file for session {session_id} not found'}
        if response.status_code == 401:
            return {'status': 'error', 'message': 'Authentication failed'}
        return {'status': 'error', 'message': f'Failed to retrieve logs: {response.text}'}

    except requests.exceptions.RequestException as e:
        return {'status': 'error', 'error': str(e), 'message': 'Failed to connect to Jesse API'}
    except Exception as e:
        return {'status': 'error', 'error': str(e), 'message': 'Failed to retrieve optimization logs'}


def _build_run_payload(session_id: str, form: dict, state: dict) -> dict:
    config = _default_optimize_config(
        form.get('exchange'),
        objective_function=form.get('objective_function', 'sharpe'),
        trials=form.get('trials', 200),
        best_candidates_count=form.get('best_candidates_count', 20),
        warm_up_candles=form.get('warm_up_candles', 210),
    )
    return {
        'id': session_id,
        'exchange': form.get('exchange'),
        'routes': form.get('routes', []),
        'data_routes': form.get('data_routes', []),
        'config': config,
        'training_start_date': form.get('training_start_date'),
        'training_finish_date': form.get('training_finish_date'),
        'testing_start_date': form.get('testing_start_date'),
        'testing_finish_date': form.get('testing_finish_date'),
        'optimal_total': int(form.get('optimal_total', 50)),
        'fast_mode': bool(form.get('fast_mode', True)),
        'cpu_cores': int(form.get('cpu_cores', _default_cpu_cores())),
        'state': state if isinstance(state, dict) else {},
    }


def _fetch_session(api_url: str, auth: str, session_id: str):
    """Fetch an optimization session and return (form, state, status, err)."""
    response = requests.post(
        f'{api_url}/optimization/sessions/{session_id}',
        headers={'Authorization': auth},
        timeout=10,
    )
    if response.status_code == 404:
        return None, None, None, {'status': 'error', 'message': f'Session {session_id} not found'}
    if response.status_code == 401:
        return None, None, None, {'status': 'error', 'message': 'Authentication failed'}
    if response.status_code != 200:
        return None, None, None, {'status': 'error', 'message': f'Failed to retrieve session: {response.text}'}

    session_data = response.json().get('session', {})
    session_status = session_data.get('status')
    state = session_data.get('state')
    if isinstance(state, str):
        try:
            state = json.loads(state)
        except json.JSONDecodeError:
            state = {}
    form = state.get('form') if isinstance(state, dict) else None
    if isinstance(form, str):
        form = json.loads(form)
    if not form:
        return None, None, session_status, {
            'status': 'error',
            'message': 'No form found in session state. Create a draft first using create_optimization_draft.',
        }
    return form, state if isinstance(state, dict) else {}, session_status, None


def _fire(api_url: str, auth: str, path: str, payload: dict) -> dict:
    response = requests.post(
        f'{api_url}{path}',
        json=payload,
        headers={'Authorization': auth},
        timeout=10,
    )
    if response.status_code in (200, 202):
        return {
            'status': 'started',
            'session_id': payload['id'],
            'dashboard_url': mcp_config.dashboard_url('optimization', payload['id']),
            'message': (
                'Optimization started. Poll get_optimization_session(session_id) until status is '
                '"finished" (or "stopped"/"terminated"). Optimization is long-running — poll less '
                'frequently (e.g. every 20-30s) and watch completed_trials / total_trials.'
            ),
        }
    if response.status_code == 401:
        return {'status': 'error', 'message': 'Authentication failed'}
    if response.status_code == 409:
        return {'status': 'error', 'message': f'Session {payload["id"]} already exists / is running.'}
    if response.status_code == 404:
        return {'status': 'error', 'message': f'Session {payload["id"]} not found'}
    return {'status': 'error', 'message': f'Failed to start optimization: {response.text}'}


def run_optimization_service(session_id: str) -> dict:
    """
    Start a previously created optimization draft.

    Goes to POST /optimization/resume (not POST /optimization): the draft row
    already exists (create_optimization_draft persisted the form), and the main
    endpoint 409s on a pre-existing row. /resume is the endpoint that requires an
    existing row and launches the worker.
    """
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth = hash_password(password)
        form, state, session_status, err = _fetch_session(api_url, auth, session_id)
        if err:
            return err

        if session_status == 'running':
            return {
                'status': 'started',
                'session_id': session_id,
                'dashboard_url': mcp_config.dashboard_url('optimization', session_id),
                'message': (
                    f'Optimization session {session_id} is already running. '
                    'Poll get_optimization_session(session_id) for progress.'
                ),
            }
        if session_status == 'finished':
            return {
                'status': 'error',
                'session_id': session_id,
                'dashboard_url': mcp_config.dashboard_url('optimization', session_id),
                'message': (
                    f'Optimization session {session_id} has already finished. Read results via '
                    'get_optimization_session(session_id), or use rerun_optimization(session_id) '
                    'to run it again, or create a new draft.'
                ),
            }

        payload = _build_run_payload(session_id, form, state)
        return _fire(api_url, auth, '/optimization/resume', payload)

    except requests.exceptions.RequestException as e:
        return {'status': 'error', 'error': str(e), 'message': 'Failed to connect to Jesse API'}
    except Exception as e:
        return {'status': 'error', 'error': str(e), 'message': 'Failed to run optimization'}


def rerun_optimization_service(session_id: str) -> dict:
    """
    Reset and restart an existing optimization session (clears prior trials/results).
    Goes to POST /optimization/rerun. Use this to re-run a finished or stopped session.
    """
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth = hash_password(password)
        form, state, session_status, err = _fetch_session(api_url, auth, session_id)
        if err:
            return err

        if session_status == 'running':
            return {
                'status': 'error',
                'session_id': session_id,
                'message': (
                    f'Optimization session {session_id} is currently running. Cancel it first '
                    '(cancel_optimization) before rerunning.'
                ),
            }

        payload = _build_run_payload(session_id, form, state)
        return _fire(api_url, auth, '/optimization/rerun', payload)

    except requests.exceptions.RequestException as e:
        return {'status': 'error', 'error': str(e), 'message': 'Failed to connect to Jesse API'}
    except Exception as e:
        return {'status': 'error', 'error': str(e), 'message': 'Failed to rerun optimization'}


def cancel_optimization_service(session_id: str) -> dict:
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth = hash_password(password)
        response = requests.post(
            f'{api_url}/optimization/cancel',
            json={'id': session_id},
            headers={'Authorization': auth},
            timeout=10,
        )
        if response.status_code == 202:
            return {'status': 'success', 'session_id': session_id,
                    'message': f'Optimization {session_id} cancellation requested'}
        if response.status_code == 401:
            return {'status': 'error', 'message': 'Authentication failed'}
        return {'status': 'error', 'message': f'Failed to cancel: {response.text}'}

    except requests.exceptions.RequestException as e:
        return {'status': 'error', 'error': str(e), 'message': 'Failed to connect to Jesse API'}
    except Exception as e:
        return {'status': 'error', 'error': str(e), 'message': 'Failed to cancel optimization'}


def terminate_optimization_service(session_id: str) -> dict:
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth = hash_password(password)
        response = requests.post(
            f'{api_url}/optimization/terminate',
            json={'id': session_id},
            headers={'Authorization': auth},
            timeout=10,
        )
        if response.status_code == 202:
            return {'status': 'success', 'session_id': session_id,
                    'message': f'Optimization {session_id} terminated'}
        if response.status_code == 401:
            return {'status': 'error', 'message': 'Authentication failed'}
        return {'status': 'error', 'message': f'Failed to terminate: {response.text}'}

    except requests.exceptions.RequestException as e:
        return {'status': 'error', 'error': str(e), 'message': 'Failed to connect to Jesse API'}
    except Exception as e:
        return {'status': 'error', 'error': str(e), 'message': 'Failed to terminate optimization'}


def purge_optimization_sessions_service(days_old: Optional[int] = None) -> dict:
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD

    try:
        auth = hash_password(password)
        payload = {'days_old': days_old}
        response = requests.post(
            f'{api_url}/optimization/purge-sessions',
            json=payload,
            headers={'Authorization': auth},
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            deleted_count = data.get('deleted_count', 0)
            return {
                'status': 'success',
                'deleted_count': deleted_count,
                'message': f'Successfully purged {deleted_count} optimization session(s)',
            }
        if response.status_code == 401:
            return {'status': 'error', 'message': 'Authentication failed'}
        return {'status': 'error', 'message': f'Failed to purge sessions: {response.text}'}

    except requests.exceptions.RequestException as e:
        return {'status': 'error', 'error': str(e), 'message': 'Failed to connect to Jesse API'}
    except Exception as e:
        return {'status': 'error', 'error': str(e), 'message': 'Failed to purge optimization sessions'}
