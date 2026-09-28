"""
Jesse Session Results and Temporary Analysis Service Functions

Thin clients for the /session-results and /analysis API routes. Jesse reads the stored
sessions, writes analysis snapshots, runs analysis code, and reads artifacts on the machine
running Jesse, so these tools work the same when the assistant runs on another computer.
"""
from typing import List, Optional

from .project_files import CANCEL_TIMEOUT_SECONDS, REQUEST_TIMEOUT_SECONDS, TRANSFER_TIMEOUT_SECONDS, _call

# Result pages are bounded by the API (128 KiB of JSON), but a large Monte Carlo record is
# parsed from the database for each page, which can take several seconds.
RESULTS_TIMEOUT_SECONDS = 60


def get_session_results_service(session_type: str, session_id: str, section: str = 'summary',
                                offset: int = 0, limit: int = 50) -> dict:
    return _call(
        'get_session_results', '/session-results/get',
        {'session_type': session_type, 'session_id': session_id, 'section': section, 'offset': offset, 'limit': limit},
        RESULTS_TIMEOUT_SECONDS,
    )


def get_live_sessions_service(limit: int = 20, offset: int = 0, status_filter: Optional[str] = None,
                              mode_filter: Optional[str] = None, title_search: Optional[str] = None) -> dict:
    return _call(
        'get_live_sessions', '/session-results/live-sessions',
        {'limit': limit, 'offset': offset, 'status_filter': status_filter, 'mode_filter': mode_filter,
         'title_search': title_search},
        RESULTS_TIMEOUT_SECONDS,
    )


def run_analysis_service(code: str, inputs: Optional[List[dict]] = None, timeout_minutes: int = 5) -> dict:
    # Writing snapshots of large sessions happens inside this request.
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
