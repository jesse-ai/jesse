"""
Run-config arguments of the MCP research draft tools (backtest, optimization, Monte Carlo,
significance test): turning them into a draft's config, describing that config in the tool
response, and changing only those fields of an existing draft.

A partial update reads the stored draft, merges the new values into its `form.config`, and saves
the whole state back with the mode's /update-state route, so the agent never has to send the full
state to change a fee or a leverage.
"""

import json
from typing import Optional

import requests

import jesse.mcp.mcp_config as mcp_config
from .auth import hash_password
from .session_config import parse_draft_config_arguments, resolve_draft_run_config

_API_PATHS = {
    'backtest': 'backtest',
    'optimization': 'optimization',
    'monte_carlo': 'monte-carlo',
    'significance_test': 'significance-test',
}
_DRAFT_NAMES = {
    'backtest': 'backtest',
    'optimization': 'optimization',
    'monte_carlo': 'Monte Carlo',
    'significance_test': 'significance test',
}


def draft_run_config(
    mode: str,
    exchange: str,
    config_overrides: object = None,
    stored: Optional[dict] = None,
    base_overrides: Optional[dict] = None,
    tool_defaults: Optional[dict] = None,
    **arguments,
) -> dict:
    """
    Validate a draft tool's run-config arguments and resolve the draft's config.

    `base_overrides` are the tool's own named mode-specific arguments (for example an
    optimization's `trials`); like the named `arguments`, they win over `config_overrides`.
    `tool_defaults` apply only to fields none of those set, ahead of the saved settings.
    Returns {'config', 'config_source', 'warnings'}; raises ValueError for invalid arguments.
    """
    overrides, warnings = parse_draft_config_arguments(
        mode, exchange, config_overrides, base=base_overrides, **arguments,
    )
    resolved = resolve_draft_run_config(mode, exchange, overrides, stored=stored, tool_defaults=tool_defaults)
    resolved['warnings'] = warnings + resolved['warnings']
    return resolved


def describe_run_config(resolved: dict) -> dict:
    """The response fields that show a draft's run config and where each value came from."""
    described = {
        'run_config': resolved['config'],
        'config_source': resolved['config_source'],
    }
    if resolved['warnings']:
        described['config_warnings'] = resolved['warnings']
    return described


def has_config_arguments(config_overrides: object = None, **arguments) -> bool:
    return config_overrides not in (None, '') or any(value is not None for value in arguments.values())


def _parse_state(session: dict) -> tuple[dict, dict]:
    state = session.get('state')
    if isinstance(state, str):
        state = json.loads(state) if state else {}
    if not isinstance(state, dict):
        state = {}
    form = state.get('form')
    if isinstance(form, str):
        form = json.loads(form)
    return state, form if isinstance(form, dict) else {}


def update_draft_run_config(
    mode: str,
    session_id: str,
    id_key: str,
    config_overrides: object = None,
    **arguments,
) -> dict:
    """Change only the run-config fields of a stored draft and save it."""
    api_url = mcp_config.JESSE_API_URL
    api_path = _API_PATHS[mode]
    name = _DRAFT_NAMES[mode]

    try:
        auth = hash_password(mcp_config.JESSE_PASSWORD)
        response = requests.post(
            f'{api_url}/{api_path}/sessions/{session_id}',
            headers={'Authorization': auth},
            timeout=10,
        )
        if response.status_code == 404:
            return {'status': 'error', 'message': f'{name.capitalize()} session {session_id} not found'}
        if response.status_code == 401:
            return {'status': 'error', 'message': 'Authentication failed'}
        if response.status_code != 200:
            return {'status': 'error', 'message': f'Failed to retrieve session: {response.text}'}

        session = response.json().get('session') or {}
        status = session.get('status')
        if status != 'draft':
            return {
                'status': 'error',
                'message': (
                    f'{name.capitalize()} session {session_id} is {status}, not a draft; its configuration '
                    f'is what it ran with. Create a new draft to run with different settings.'
                ),
            }
        state, form = _parse_state(session)
        exchange = form.get('exchange')
        if not exchange:
            return {'status': 'error', 'message': f'The draft has no exchange; create it again with create_{mode}_draft.'}

        try:
            resolved = draft_run_config(
                mode, exchange, config_overrides, stored=form.get('config'), **arguments,
            )
        except ValueError as e:
            return {'status': 'error', 'message': str(e)}

        form['config'] = resolved['config']
        state['form'] = form
        response = requests.post(
            f'{api_url}/{api_path}/update-state',
            json={'id': session_id, 'state': state},
            headers={'Authorization': auth},
            timeout=10,
        )
        if response.status_code == 401:
            return {'status': 'error', 'message': 'Authentication failed'}
        if response.status_code != 200:
            return {'status': 'error', 'message': f'Failed to update {name} draft: {response.text}'}

        return {
            'status': 'success',
            id_key: session_id,
            'draft_state': state,
            **describe_run_config(resolved),
            'dashboard_url': mcp_config.dashboard_url(mode, session_id),
            'message': f'{name.capitalize()} draft configuration updated',
        }
    except requests.exceptions.RequestException as e:
        return {'status': 'error', 'error': str(e), 'message': 'Failed to connect to Jesse API'}
    except Exception as e:
        return {'status': 'error', 'error': str(e), 'message': f'Failed to update {name} draft'}
