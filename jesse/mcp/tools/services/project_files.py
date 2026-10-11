"""
Jesse Project File and Research Script Service Functions

Thin clients for the /project-files and /research-scripts API routes. Jesse performs every
file operation and script run on the machine running Jesse, confined to strategies/ and
research_scripts/ in the project, so they work the same when the assistant runs on another
computer or Jesse runs in Docker.
"""
from typing import List, Optional

import requests

from .auth import hash_password
import jesse.mcp.mcp_config as mcp_config

# Reads, writes, and job status answer immediately.
REQUEST_TIMEOUT_SECONDS = 15
# Copies (up to 1 GiB) and recursive moves/deletes run inside one API request.
TRANSFER_TIMEOUT_SECONDS = 120
# Cancelling waits up to 12 seconds for the process group to stop (research_jobs.cancel_job).
CANCEL_TIMEOUT_SECONDS = 30

# Where operations happen, spelled out because the assistant may run on another machine.
LOCATION = (
    'On the machine running Jesse, inside the Jesse project folder. '
    "Not in the assistant's local workspace."
)


def _call(action: str, route: str, payload: dict, timeout: float = REQUEST_TIMEOUT_SECONDS) -> dict:
    """POST to a Jesse API route and return its result, or an error with a stable error_type."""
    failed = {'status': 'error', 'action': action}
    if not mcp_config.JESSE_API_URL or not mcp_config.JESSE_PASSWORD:
        return {**failed, 'error_type': 'config_error', 'message': 'The MCP worker is missing its Jesse API configuration.'}
    try:
        response = requests.post(
            f'{mcp_config.JESSE_API_URL}{route}',
            json=payload,
            headers={'Authorization': hash_password(mcp_config.JESSE_PASSWORD)},  # Jesse uses the hash directly, not Bearer
            timeout=timeout,
        )
    except requests.exceptions.RequestException as e:
        return {**failed, 'error_type': 'connection_error', 'message': 'Could not connect to Jesse API', 'details': str(e)}

    if response.status_code == 401:
        return {**failed, 'error_type': 'authentication_failed', 'message': 'Invalid password provided'}
    try:
        data = response.json()
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}

    if response.status_code == 200 and data.get('status') == 'success':
        return {'action': action, **data, 'location': LOCATION}
    if data.get('error_type'):
        return {**failed, 'error_type': data['error_type'], 'message': data.get('message', '')}
    return {**failed, 'error_type': 'http_error', 'http_status': response.status_code, 'message': data.get('message', response.text)}


def list_project_files_service(path: str = '', recursive: bool = False, max_entries: int = 200) -> dict:
    return _call('list_project_files', '/project-files/list', {'path': path, 'recursive': recursive, 'max_entries': max_entries})


def read_project_file_service(path: str, start_line: int = 1, max_lines: int = 400) -> dict:
    return _call('read_project_file', '/project-files/read', {'path': path, 'start_line': start_line, 'max_lines': max_lines})


def write_project_file_service(path: str, content: str, overwrite: bool = False) -> dict:
    return _call('write_project_file', '/project-files/write', {'path': path, 'content': content, 'overwrite': overwrite})


def create_project_directory_service(path: str) -> dict:
    return _call('create_project_directory', '/project-files/mkdir', {'path': path})


def move_project_path_service(source: str, destination: str, overwrite: bool = False) -> dict:
    return _call(
        'move_project_path', '/project-files/move',
        {'source': source, 'destination': destination, 'overwrite': overwrite}, TRANSFER_TIMEOUT_SECONDS,
    )


def copy_project_path_service(source: str, destination: str, overwrite: bool = False) -> dict:
    return _call(
        'copy_project_path', '/project-files/copy',
        {'source': source, 'destination': destination, 'overwrite': overwrite}, TRANSFER_TIMEOUT_SECONDS,
    )


def delete_project_path_service(path: str, recursive: bool = False) -> dict:
    return _call('delete_project_path', '/project-files/delete', {'path': path, 'recursive': recursive}, TRANSFER_TIMEOUT_SECONDS)


def run_research_script_service(path: str, args: Optional[List[str]] = None, timeout_minutes: int = 60) -> dict:
    return _call(
        'run_research_script', '/research-scripts/run',
        {'path': path, 'args': list(args or []), 'timeout_minutes': timeout_minutes},
    )


def get_research_job_status_service(job_id: str = '') -> dict:
    return _call('get_research_job_status', '/research-scripts/jobs', {'job_id': job_id})


def get_research_job_output_service(job_id: str, tail_lines: int = 200) -> dict:
    return _call('get_research_job_output', '/research-scripts/output', {'job_id': job_id, 'tail_lines': tail_lines})


def cancel_research_job_service(job_id: str) -> dict:
    return _call('cancel_research_job', '/research-scripts/cancel', {'job_id': job_id}, CANCEL_TIMEOUT_SECONDS)
