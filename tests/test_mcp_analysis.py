"""
Temporary analysis jobs: session snapshots, real Python/matplotlib runs, artifact retrieval
as MCP image content, confinement, cancellation, cleanup, and the shared job engine.

Session exports are replaced with realistic stand-ins (the database is covered by the
disposable-instance integration test). Every job here is a small disposable script; none
touches the database, the network, or an exchange.
"""
import asyncio
import base64
import io
import json
import os
import sys
import time
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp.types import CallToolResult, ImageContent, TextContent

import jesse.mcp.tools.services.project_files as project_files_service
from jesse.controllers import analysis_controller, research_scripts_controller
from jesse.mcp import server as mcp_server
from jesse.mcp.agent_rules import _load_packaged_rules
from jesse.mcp.resources import register_resources
from jesse.mcp.tools import register_tools
from jesse.mcp.tools.analysis import artifact_result
from jesse.services import analysis_jobs, auth, research_jobs, session_results
from tests.mcp_tool_adapters import callable_tool


# The real exporter, captured before the fixture replaces it with _export.
_REAL_EXPORT = session_results.export_session
PASSWORD = 'analysis-password'
HEADERS = {'Authorization': sha256(PASSWORD.encode('utf-8')).hexdigest()}
WAIT_SECONDS = 60
BACKTEST_A = '11111111-1111-4111-8111-111111111111'
BACKTEST_B = '22222222-2222-4222-8222-222222222222'
LIVE_ID = '55555555-5555-4555-8555-555555555555'

CHART_CODE = '''
import json
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(6, 3))
for name in ("base", "tuned"):
    data = json.load(open(f"inputs/{name}.json"))
    curve = next(s for s in data["equity_curve"] if s["name"] == "Portfolio")
    ax.plot([p["value"] for p in curve["data"]], label=name)
    print(name, len(data["trades"]), data["metrics"]["sharpe_ratio"])
ax.legend()
import os
os.makedirs("output/charts", exist_ok=True)
fig.savefig("output/charts/equity.png", dpi=80)
plt.close(fig)
open("output/summary.csv", "w").write("name,sharpe\\nbase,1.1\\ntuned,1.7\\n")
'''

SPAWNER = '''
import subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
open("output/child.pid", "w").write(str(child.pid))
print("spawned", flush=True)
time.sleep(120)
'''


class FakeMCP:
    def __init__(self):
        self.tools = {}
        self.resources = {}

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = callable_tool(func)
            return func
        return decorator

    def resource(self, uri):
        def decorator(func):
            self.resources[uri] = func
            return func
        return decorator


def _export(session_type: str, session_id: str) -> dict:
    """What export_session returns for a stored backtest (see test_mcp_session_results.py)."""
    if session_id not in (BACKTEST_A, BACKTEST_B):
        raise session_results.ProjectFileError('not_found', f'Backtest session {session_id} does not exist.', 404)
    boost = 2 if session_id == BACKTEST_B else 1
    return {
        'summary': {'session_type': session_type, 'session_id': session_id, 'session_status': 'finished', 'title': f't{boost}'},
        'metrics': {'sharpe_ratio': 1.1 * boost},
        'trades': [{'id': f'trade-{i}', 'PNL': float(i)} for i in range(5 * boost)],
        'equity_curve': [{'name': 'Portfolio', 'data': [{'time': 1735689600 + d * 86400, 'value': 10_000 + d * boost} for d in range(60)]}],
        'hyperparameters': [],
    }


@pytest.fixture
def project(tmp_path, monkeypatch) -> Path:
    root = tmp_path / 'project'
    (root / 'storage').mkdir(parents=True)
    (root / 'research_scripts').mkdir()
    (root / 'strategies').mkdir()
    monkeypatch.chdir(root)
    monkeypatch.setattr(research_jobs, 'TERMINATE_GRACE_SECONDS', 1.0)
    monkeypatch.setattr(research_jobs, '_POLL_SECONDS', 0.05)
    monkeypatch.setattr(session_results, 'export_session', _export)
    yield root
    research_jobs.terminate_all_jobs()
    with research_jobs._jobs_lock:
        research_jobs._jobs.clear()
    analysis_jobs._preparing.clear()


@pytest.fixture
def api(monkeypatch) -> TestClient:
    monkeypatch.setitem(auth.ENV_VALUES, 'PASSWORD', PASSWORD)
    app = FastAPI()

    @app.exception_handler(auth.InvalidAuthError)
    async def invalid_auth_handler(_request, _exc):
        return auth.unauthorized_response()

    app.include_router(analysis_controller.router)
    app.include_router(research_scripts_controller.router)
    return TestClient(app)


def _post(api, route: str, payload: dict, expect: int = 200) -> dict:
    response = api.post(f'/analysis/{route}', json=payload, headers=HEADERS)
    assert response.status_code == expect, response.text
    return response.json()


def _refused(api, route, payload, status_code, error_type) -> dict:
    body = _post(api, route, payload, status_code)
    assert (body['status'], body['error_type']) == ('error', error_type), body
    return body


INPUTS = [{'session_type': 'backtest', 'session_id': BACKTEST_A, 'name': 'base'},
          {'session_type': 'backtest', 'session_id': BACKTEST_B, 'name': 'tuned'}]


def _run(api, code: str, inputs=None, timeout_minutes: int = 5) -> dict:
    return _post(api, 'run', {'code': code, 'inputs': inputs or [], 'timeout_minutes': timeout_minutes})['job']


def _wait(api, job_id: str) -> dict:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        body = _post(api, 'jobs', {'job_id': job_id, 'tail_lines': 200})
        if body['job']['status'] != 'running':
            return body
        time.sleep(0.05)
    raise AssertionError(f'analysis job {job_id} did not finish')


def _workspace(project: Path, job_id: str) -> Path:
    return project / 'storage' / 'mcp' / 'analysis' / job_id


def _artifact(api, job_id: str, path: str, expect: int = 200) -> dict:
    return _post(api, 'artifact', {'job_id': job_id, 'path': path}, expect)


def _pid_gone(pid: int) -> bool:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


def _wait_for_file(path: Path) -> str:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        if path.exists() and path.read_text().strip():
            return path.read_text().strip()
        time.sleep(0.05)
    raise AssertionError(f'{path} was never written')


def _png(width: int = 4, height: int = 3) -> bytes:
    from PIL import Image
    buffer = io.BytesIO()
    Image.new('RGB', (width, height), (10, 20, 30)).save(buffer, format='PNG')
    return buffer.getvalue()


def _finished_job(api, project, code='print("ok")\n') -> str:
    job = _run(api, code)
    assert _wait(api, job['id'])['job']['status'] == 'succeeded'
    return job['id']


# ---------------------------------------------------------------------------
# The full flow
# ---------------------------------------------------------------------------

def test_every_analysis_route_requires_authentication(project, api):
    for route in ('run', 'jobs', 'cancel', 'delete', 'artifact'):
        response = api.post(f'/analysis/{route}', json={'code': 'x', 'job_id': 'a' * 32, 'path': 'a.png'},
                            headers={'Authorization': 'wrong'})
        assert response.status_code == 401


def test_snapshots_code_chart_and_table_flow(project, api):
    job = _run(api, CHART_CODE, INPUTS)

    assert job['status'] == 'running' and job['kind'] == 'analysis'
    assert job['workspace'] == f'storage/mcp/analysis/{job["id"]}'
    assert [(i['name'], i['file'], i['session_status']) for i in job['inputs']] == [
        ('base', 'inputs/base.json', 'finished'), ('tuned', 'inputs/tuned.json', 'finished')]
    assert job['expires_at'] is None and '24 hours' in job['lifetime']
    workspace = _workspace(project, job['id'])
    # The snapshot is exactly the export, written by Jesse; nothing went through the assistant.
    assert json.loads((workspace / 'inputs' / 'tuned.json').read_text()) == _export('backtest', BACKTEST_B)
    assert json.loads((workspace / 'inputs' / 'manifest.json').read_text()) == job['inputs']
    assert (workspace / 'analysis.py').read_text() == CHART_CODE
    assert not any((project / 'research_scripts').iterdir())  # nothing written to the project's folders

    finished = _wait(api, job['id'])

    assert finished['job']['status'] == 'succeeded' and finished['job']['exit_code'] == 0
    assert finished['output'] == 'base 5 1.1\ntuned 10 2.2\n'
    assert finished['job']['expires_at'] is not None
    assert {a['path']: (a['kind'], a.get('mime_type')) for a in finished['artifacts']} == {
        'charts/equity.png': ('image', 'image/png'), 'summary.csv': ('text', None)}

    image = _artifact(api, job['id'], 'charts/equity.png')
    data = base64.b64decode(image['data_base64'])
    assert data.startswith(b'\x89PNG') and len(data) == image['size_bytes']
    assert (image['kind'], image['mime_type'], image['width'], image['height']) == ('image', 'image/png', 480, 240)
    assert _artifact(api, job['id'], 'output/charts/equity.png')['data_base64'] == image['data_base64']
    table = _artifact(api, job['id'], 'summary.csv')
    assert (table['kind'], table['content'], table['truncated']) == ('text', 'name,sharpe\nbase,1.1\ntuned,1.7\n', False)


def test_research_and_analysis_jobs_are_separate_scopes(project, api):
    analysis = _finished_job(api, project)
    response = api.post('/research-scripts/jobs', json={'job_id': analysis}, headers=HEADERS)
    assert response.status_code == 404  # an analysis job is not a research job
    assert analysis not in [job['id'] for job in api.post('/research-scripts/jobs', json={}, headers=HEADERS).json()['jobs']]
    assert not (project / 'storage' / 'research-jobs').exists()
    assert analysis in [job['id'] for job in _post(api, 'jobs', {})['jobs']]


def test_concurrency_limit_is_per_scope(project, api):
    sleeper = 'import time\ntime.sleep(120)\n'
    jobs = [_run(api, sleeper) for _ in range(analysis_jobs.MAX_CONCURRENT_ANALYSIS_JOBS)]
    body = _refused(api, 'run', {'code': sleeper}, 429, 'too_many_jobs')
    assert 'analysis jobs' in body['message']
    # No workspace is created for the refused job.
    assert len(list((project / 'storage' / 'mcp' / 'analysis').iterdir())) == len(jobs)

    (project / 'research_scripts' / 'ok.py').write_text('print(1)\n')
    research = api.post('/research-scripts/run', json={'path': 'research_scripts/ok.py'}, headers=HEADERS)
    assert research.status_code == 200, research.text  # research jobs are not blocked by analyses
    for job in jobs:
        assert _post(api, 'cancel', {'job_id': job['id']})['job']['status'] == 'cancelled'


# ---------------------------------------------------------------------------
# Validation and preparation failures
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('payload, status_code, error_type', [
    ({'code': '   '}, 400, 'invalid_request'),
    ({'code': 'x', 'timeout_minutes': 0}, 400, 'invalid_request'),
    ({'code': 'x', 'timeout_minutes': analysis_jobs.MAX_TIMEOUT_MINUTES + 1}, 400, 'invalid_request'),
    ({'code': 'x', 'inputs': [{'session_type': 'nope', 'session_id': BACKTEST_A}]}, 400, 'invalid_request'),
    ({'code': 'x', 'inputs': [{'session_type': 'backtest', 'session_id': BACKTEST_A, 'name': '../evil'}]}, 400, 'invalid_request'),
    ({'code': 'x', 'inputs': [{'session_type': 'backtest', 'session_id': BACKTEST_A, 'name': 'manifest'}]}, 400, 'invalid_request'),
    ({'code': 'x', 'inputs': [{'session_type': 'backtest', 'session_id': BACKTEST_A, 'name': 'a'},
                              {'session_type': 'backtest', 'session_id': BACKTEST_B, 'name': 'a'}]}, 400, 'invalid_request'),
    ({'code': 'x', 'inputs': [{'session_type': 'backtest', 'session_id': BACKTEST_A}] * (analysis_jobs.MAX_INPUTS + 1)},
     400, 'invalid_request'),
])
def test_invalid_runs_are_refused_without_a_workspace(project, api, payload, status_code, error_type):
    _refused(api, 'run', payload, status_code, error_type)
    assert not (project / 'storage' / 'mcp' / 'analysis').exists() or not any((project / 'storage' / 'mcp' / 'analysis').iterdir())


def test_code_size_limit(project, api, monkeypatch):
    monkeypatch.setattr(analysis_jobs, 'MAX_CODE_BYTES', 10)
    _refused(api, 'run', {'code': 'print("more than ten bytes")'}, 413, 'too_large')


def test_failed_snapshots_remove_the_workspace(project, api, monkeypatch):
    missing = '99999999-9999-4999-8999-999999999999'
    _refused(api, 'run', {'code': 'x', 'inputs': [{'session_type': 'backtest', 'session_id': missing}]}, 404, 'not_found')
    monkeypatch.setattr(analysis_jobs, 'MAX_INPUT_BYTES', 200)
    body = _refused(api, 'run', {'code': 'x', 'inputs': INPUTS}, 413, 'too_large')
    assert 'snapshot' in body['message']
    monkeypatch.setattr(analysis_jobs, 'MAX_INPUT_BYTES', 64 * 1024 * 1024)
    monkeypatch.setattr(analysis_jobs, 'MAX_TOTAL_INPUT_BYTES', 3000)
    _refused(api, 'run', {'code': 'x', 'inputs': INPUTS}, 413, 'too_large')

    def broken(_type, _id):
        raise RuntimeError('database went away: password=hunter2')

    monkeypatch.setattr(session_results, 'export_session', broken)
    body = _refused(api, 'run', {'code': 'x', 'inputs': INPUTS[:1]}, 500, 'read_failed')
    assert 'hunter2' not in json.dumps(body)
    assert list((project / 'storage' / 'mcp' / 'analysis').iterdir()) == []


def test_live_inputs_respect_the_live_plugin_gate(project, api, monkeypatch):
    monkeypatch.setattr(session_results, 'export_session', _REAL_EXPORT)
    monkeypatch.setattr(session_results, '_live_plugin_available', lambda: False)
    _refused(api, 'run', {'code': 'x', 'inputs': [{'session_type': 'live', 'session_id': LIVE_ID}]}, 403, 'live_plugin_unavailable')
    assert list((project / 'storage' / 'mcp' / 'analysis').iterdir()) == []


# ---------------------------------------------------------------------------
# Job lifecycle
# ---------------------------------------------------------------------------

def test_failures_report_the_traceback(project, api):
    job = _run(api, 'import sys\nprint("before")\nraise ValueError("bad column")\n')
    finished = _wait(api, job['id'])
    assert finished['job']['status'] == 'failed' and finished['job']['exit_code'] == 1
    assert 'before' in finished['output'] and 'ValueError: bad column' in finished['output']


def test_timeout_and_cancel_stop_the_job_and_its_children(project, api, monkeypatch):
    job = _run(api, SPAWNER)
    child = int(_wait_for_file(_workspace(project, job['id']) / 'output' / 'child.pid'))
    cancelled = _post(api, 'cancel', {'job_id': job['id']})
    assert cancelled['cancel_requested'] is True and cancelled['job']['status'] == 'cancelled'
    assert _pid_gone(job['pid']) and _pid_gone(child)
    assert _post(api, 'cancel', {'job_id': job['id']})['cancel_requested'] is False

    monkeypatch.setattr(research_jobs, '_deadline', lambda minutes: time.monotonic() + 0.5)
    timed = _run(api, SPAWNER)
    child = int(_wait_for_file(_workspace(project, timed['id']) / 'output' / 'child.pid'))
    assert _wait(api, timed['id'])['job']['status'] == 'timed_out'
    assert _pid_gone(child)


def test_shutdown_interrupts_analysis_jobs(project, api):
    job = _run(api, 'import time\ntime.sleep(120)\n')
    research_jobs.terminate_all_jobs()
    assert _wait(api, job['id'])['job']['status'] == 'interrupted'
    assert _pid_gone(job['pid'])


def test_a_record_left_running_by_a_previous_process_is_interrupted(project, api):
    job_id = 'c' * 32
    workspace = _workspace(project, job_id)
    (workspace / 'output').mkdir(parents=True)
    (workspace / 'job.json').write_text(json.dumps({'id': job_id, 'status': 'running', 'started_at': '2026-09-01T00:00:00+00:00'}))
    body = _post(api, 'jobs', {'job_id': job_id})
    assert body['job']['status'] == 'interrupted' and 'no longer tracked' in body['job']['message']
    assert body['job']['expires_at'] is not None and body['output'] == ''


def test_console_output_is_capped(project, api, monkeypatch):
    monkeypatch.setattr(analysis_jobs, 'MAX_LOG_BYTES', 1000)
    job = _run(api, 'print("x" * 5000)\n')
    finished = _wait(api, job['id'])
    assert finished['output_truncated'] is True
    assert (_workspace(project, job['id']) / 'console.txt').stat().st_size < 1200


# ---------------------------------------------------------------------------
# Artifact confinement and validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('path, status_code, error_type', [
    ('../job.json', 400, 'invalid_path'),
    ('output/../inputs/manifest.json', 400, 'invalid_path'),
    ('/etc/passwd', 400, 'invalid_path'),
    ('~/.ssh/id_rsa', 400, 'invalid_path'),
    ('C:/windows/win.ini', 400, 'invalid_path'),
    ('charts\\x.png', 400, 'invalid_path'),
    ('output', 400, 'invalid_path'),
    ('inputs/manifest.json', 404, 'not_found'),  # resolved inside output/, where it does not exist
    ('analysis.py', 404, 'not_found'),
    ('missing.png', 404, 'not_found'),
])
def test_artifacts_are_confined_to_the_output_folder(project, api, path, status_code, error_type):
    job_id = _finished_job(api, project)
    _refused(api, 'artifact', {'job_id': job_id, 'path': path}, status_code, error_type)


def test_symlinks_in_the_output_folder_are_never_followed(project, api, tmp_path):
    job_id = _finished_job(api, project)
    output = _workspace(project, job_id) / 'output'
    secret = tmp_path / 'secret.png'
    secret.write_bytes(_png())
    (output / 'link.png').symlink_to(secret)
    (output / 'inputs').symlink_to(_workspace(project, job_id) / 'inputs', target_is_directory=True)
    (output / 'dir').mkdir()
    other = _finished_job(api, project)
    (output / 'dir' / 'other').symlink_to(_workspace(project, other), target_is_directory=True)

    _refused(api, 'artifact', {'job_id': job_id, 'path': 'link.png'}, 403, 'unsafe_path')
    _refused(api, 'artifact', {'job_id': job_id, 'path': 'inputs/manifest.json'}, 403, 'unsafe_path')
    _refused(api, 'artifact', {'job_id': job_id, 'path': 'dir/other/job.json'}, 403, 'unsafe_path')
    listed = {a['path']: a['kind'] for a in _post(api, 'jobs', {'job_id': job_id})['artifacts']}
    assert listed == {'dir/other': 'symlink', 'inputs': 'symlink', 'link.png': 'symlink'}


def test_artifacts_belong_to_their_own_job(project, api):
    first = _finished_job(api, project, 'import os\nopen("output/mine.txt", "w").write("first")\n')
    second = _finished_job(api, project)
    assert _artifact(api, first, 'mine.txt')['content'] == 'first'
    _refused(api, 'artifact', {'job_id': second, 'path': 'mine.txt'}, 404, 'not_found')
    _refused(api, 'artifact', {'job_id': 'not-a-job', 'path': 'mine.txt'}, 400, 'invalid_request')
    _refused(api, 'artifact', {'job_id': 'f' * 32, 'path': 'mine.txt'}, 404, 'not_found')


def test_image_formats_sizes_and_dimensions_are_validated(project, api, monkeypatch):
    from PIL import Image
    job_id = _finished_job(api, project)
    output = _workspace(project, job_id) / 'output'
    for fmt, mime in (('JPEG', 'image/jpeg'), ('GIF', 'image/gif'), ('WEBP', 'image/webp'), ('PNG', 'image/png')):
        Image.new('RGB', (37, 21), (200, 10, 10)).save(output / f'img.{fmt.lower()}', format=fmt)
        image = _artifact(api, job_id, f'img.{fmt.lower()}')
        assert (image['mime_type'], image['width'], image['height']) == (mime, 37, 21), fmt
    lossless = io.BytesIO()
    Image.new('RGBA', (19, 7)).save(lossless, format='WEBP', lossless=True)
    (output / 'lossless.webp').write_bytes(lossless.getvalue())
    assert (_artifact(api, job_id, 'lossless.webp')['width'], _artifact(api, job_id, 'lossless.webp')['height']) == (19, 7)

    (output / 'fake.png').write_bytes(b'\x89PNG\r\n\x1a\n' + b'garbage' * 20)
    _refused(api, 'artifact', {'job_id': job_id, 'path': 'fake.png'}, 422, 'invalid_image')
    (output / 'wide.png').write_bytes(_png(60, 2))
    monkeypatch.setattr(analysis_jobs, 'MAX_IMAGE_DIMENSION', 50)
    _refused(api, 'artifact', {'job_id': job_id, 'path': 'wide.png'}, 413, 'artifact_too_large')
    monkeypatch.setattr(analysis_jobs, 'MAX_IMAGE_BYTES', 50)
    body = _refused(api, 'artifact', {'job_id': job_id, 'path': 'img.png'}, 413, 'artifact_too_large')
    assert 'dpi' in body['message']

    (output / 'model.pkl').write_bytes(b'\x80\x04\x95\x00binary')
    binary = _artifact(api, job_id, 'model.pkl')
    assert binary['kind'] == 'binary' and 'content' not in binary and 'data_base64' not in binary
    (output / 'fake.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    assert _artifact(api, job_id, 'fake.svg')['kind'] == 'text'
    os.mkfifo(output / 'pipe')
    _refused(api, 'artifact', {'job_id': job_id, 'path': 'pipe'}, 409, 'wrong_type')


def test_text_artifacts_and_listings_are_bounded(project, api, monkeypatch):
    job_id = _finished_job(api, project)
    output = _workspace(project, job_id) / 'output'
    (output / 'big.txt').write_text('é' * 100)
    for i in range(5):
        (output / f'f{i}.txt').write_text('x')
    monkeypatch.setattr(analysis_jobs, 'MAX_TEXT_ARTIFACT_CHARS', 10)
    text = _artifact(api, job_id, 'big.txt')
    assert text['content'] == 'é' * 10 and text['truncated'] is True
    monkeypatch.setattr(analysis_jobs, 'MAX_ARTIFACTS_LISTED', 3)
    listed = _post(api, 'jobs', {'job_id': job_id})
    assert len(listed['artifacts']) == 3 and listed['artifacts_truncated'] is True


# ---------------------------------------------------------------------------
# Cleanup, deletion, and races
# ---------------------------------------------------------------------------

def _age(project: Path, job_id: str, hours: float) -> None:
    """Rewrite a finished job's record as if it had finished `hours` ago."""
    record_path = _workspace(project, job_id) / 'job.json'
    record = json.loads(record_path.read_text())
    finished = time.time() - hours * 3600
    from datetime import datetime, timezone
    record['finished_at'] = datetime.fromtimestamp(finished, timezone.utc).isoformat(timespec='seconds')
    record_path.write_text(json.dumps(record))


def test_cleanup_removes_expired_and_excess_workspaces_but_never_running_ones(project, api, monkeypatch):
    expired = _finished_job(api, project)
    fresh = _finished_job(api, project)
    # Started before the record is aged, because starting a job runs cleanup itself.
    running = _run(api, 'import time\ntime.sleep(120)\n')['id']
    _age(project, expired, analysis_jobs.RETENTION_HOURS + 1)
    record = json.loads((_workspace(project, running) / 'job.json').read_text())
    record['started_at'] = '2000-01-01T00:00:00+00:00'  # ancient, but still running here
    (_workspace(project, running) / 'job.json').write_text(json.dumps(record))
    preparing = 'd' * 32
    (_workspace(project, preparing)).mkdir()
    analysis_jobs._preparing.add(preparing)
    orphan = 'e' * 32
    _workspace(project, orphan).mkdir()
    os.utime(_workspace(project, orphan), (time.time() - 7200, time.time() - 7200))
    trash = project / 'storage' / 'mcp' / 'analysis' / f'.trash-{"f" * 32}-x'
    (trash / 'output').mkdir(parents=True)

    removed = analysis_jobs.cleanup_workspaces()

    assert set(removed) == {expired, orphan}
    remaining = {p.name for p in (project / 'storage' / 'mcp' / 'analysis').iterdir()}
    assert remaining == {fresh, running, preparing}
    _refused(api, 'jobs', {'job_id': expired}, 404, 'not_found')

    monkeypatch.setattr(analysis_jobs, 'MAX_KEPT_JOBS', 0)
    assert analysis_jobs.cleanup_workspaces() == [fresh]
    assert _workspace(project, running).exists() and _workspace(project, preparing).exists()
    _post(api, 'cancel', {'job_id': running})


def test_cleanup_enforces_the_storage_cap_oldest_first(project, api, monkeypatch):
    old = _finished_job(api, project, 'open("output/data.bin", "wb").write(b"x" * 4000)\n')
    new = _finished_job(api, project, 'open("output/data.bin", "wb").write(b"x" * 4000)\n')
    _age(project, old, 2)
    _age(project, new, 1)
    # Each workspace holds a little over 4000 bytes, so only the newer one fits under the cap.
    monkeypatch.setattr(analysis_jobs, 'MAX_STORAGE_BYTES', 6000)
    assert analysis_jobs.cleanup_workspaces() == [old]
    assert _workspace(project, new).exists()


def test_new_runs_trigger_cleanup(project, api):
    expired = _finished_job(api, project)
    _age(project, expired, analysis_jobs.RETENTION_HOURS + 1)
    _finished_job(api, project)
    assert not _workspace(project, expired).exists()


def test_delete_refuses_running_jobs_and_removes_finished_ones(project, api):
    running = _run(api, 'import time\ntime.sleep(120)\n')['id']
    _refused(api, 'delete', {'job_id': running}, 409, 'job_running')
    _post(api, 'cancel', {'job_id': running})
    assert _post(api, 'delete', {'job_id': running}) == {'status': 'success', 'job_id': running, 'deleted': True}
    body = _refused(api, 'jobs', {'job_id': running}, 404, 'not_found')
    assert 'cleaned up' in body['message']
    _refused(api, 'delete', {'job_id': running}, 404, 'not_found')


def test_an_artifact_being_read_survives_deletion_and_later_reads_fail_cleanly(project, api, monkeypatch):
    job_id = _finished_job(api, project, 'open("output/chart.png", "wb").write(__import__("base64").b64decode("%s"))\n'
                           % base64.b64encode(_png(8, 8)).decode())
    real_size = analysis_jobs._image_size

    def delete_mid_read(data, mime):
        analysis_jobs.delete_job(job_id)  # cleanup/deletion races with the open file
        return real_size(data, mime)

    monkeypatch.setattr(analysis_jobs, '_image_size', delete_mid_read)
    image = _artifact(api, job_id, 'chart.png')
    assert base64.b64decode(image['data_base64']) == _png(8, 8)
    assert not _workspace(project, job_id).exists()
    monkeypatch.setattr(analysis_jobs, '_image_size', real_size)
    _refused(api, 'artifact', {'job_id': job_id, 'path': 'chart.png'}, 404, 'not_found')


def test_a_workspace_that_cannot_be_removed_never_blocks_runs_or_deletes(project, api):
    expired = _finished_job(api, project, 'import os\nos.makedirs("output/locked")\nopen("output/locked/f", "w").write("x")\n'
                            'os.chmod("output/locked", 0o500)\n')
    deleted = _finished_job(api, project, 'import os\nos.makedirs("output/locked")\nopen("output/locked/f", "w").write("x")\n'
                            'os.chmod("output/locked", 0o500)\n')
    _age(project, expired, analysis_jobs.RETENTION_HOURS + 1)
    root = project / 'storage' / 'mcp' / 'analysis'
    try:
        # The next run still starts and the expired job is gone, although its files stay as trash.
        _finished_job(api, project)
        _refused(api, 'jobs', {'job_id': expired}, 404, 'not_found')
        assert _post(api, 'delete', {'job_id': deleted})['deleted'] is True
        _refused(api, 'jobs', {'job_id': deleted}, 404, 'not_found')
        trash = [path for path in root.iterdir() if path.name.startswith('.trash-')]
        if os.geteuid() != 0:  # root can remove the folder despite its permissions
            assert len(trash) == 2
    finally:
        for locked in root.glob('.trash-*/output/locked'):
            locked.chmod(0o700)
    # Once removable, the leftovers go with the next cleanup.
    analysis_jobs.cleanup_workspaces()
    assert not [path for path in root.iterdir() if path.name.startswith('.trash-')]


def test_oversized_images_are_reported_as_too_large_before_the_decompression_bomb_check(project, api, monkeypatch):
    from PIL import Image
    job_id = _finished_job(api, project)
    (_workspace(project, job_id) / 'output' / 'huge.png').write_bytes(_png(60, 40))
    # Pillow refuses images over twice this many pixels as decompression bombs.
    monkeypatch.setattr(Image, 'MAX_IMAGE_PIXELS', 1000)
    monkeypatch.setattr(analysis_jobs, 'MAX_IMAGE_DIMENSION', 50)
    body = _refused(api, 'artifact', {'job_id': job_id, 'path': 'huge.png'}, 413, 'artifact_too_large')
    assert '60x40' in body['message'] and 'dpi' in body['message']


def test_the_production_limits_match_the_documented_values():
    assert analysis_jobs.ANALYSIS_ROOT == os.path.join('storage', 'mcp', 'analysis')
    assert (analysis_jobs.DEFAULT_TIMEOUT_MINUTES, analysis_jobs.MAX_TIMEOUT_MINUTES) == (5, 30)
    assert analysis_jobs.MAX_CONCURRENT_ANALYSIS_JOBS == 2
    assert analysis_jobs.MAX_CODE_BYTES == 256 * 1024
    assert (analysis_jobs.MAX_INPUTS, analysis_jobs.MAX_INPUT_BYTES, analysis_jobs.MAX_TOTAL_INPUT_BYTES) == (
        10, 64 * 1024 * 1024, 256 * 1024 * 1024)
    assert (analysis_jobs.RETENTION_HOURS, analysis_jobs.MAX_KEPT_JOBS, analysis_jobs.MAX_STORAGE_BYTES) == (
        24, 50, 2 * 1024 ** 3)
    assert (analysis_jobs.MAX_IMAGE_BYTES, analysis_jobs.MAX_IMAGE_DIMENSION) == (3 * 1024 * 1024, 8000)
    assert analysis_jobs.MAX_LOG_BYTES == 5 * 1024 * 1024


# ---------------------------------------------------------------------------
# MCP tools, image content, and guidance
# ---------------------------------------------------------------------------

@pytest.fixture
def forward_to_api(api, monkeypatch):
    def forward_post(url, json=None, headers=None, timeout=None):
        return api.post(url.removeprefix('http://jesse.test'), json=json, headers=headers)

    monkeypatch.setattr(project_files_service.mcp_config, 'JESSE_API_URL', 'http://jesse.test')
    monkeypatch.setattr(project_files_service.mcp_config, 'JESSE_PASSWORD', PASSWORD)
    monkeypatch.setattr(project_files_service.requests, 'post', forward_post)


def test_mcp_tools_run_poll_fetch_images_and_clean_up(project, forward_to_api):
    mcp = FakeMCP()
    register_tools(mcp)
    tools = mcp.tools

    started = tools['run_analysis'](CHART_CODE, INPUTS)
    assert started['status'] == 'success' and 'machine running Jesse' in started['location']
    job_id = started['job']['id']
    deadline = time.monotonic() + WAIT_SECONDS
    while tools['get_analysis_job'](job_id)['job']['status'] == 'running' and time.monotonic() < deadline:
        time.sleep(0.05)
    status = tools['get_analysis_job'](job_id)
    assert status['job']['status'] == 'succeeded' and 'tuned 10' in status['output']

    result = tools['get_analysis_artifact'](job_id, 'charts/equity.png')
    assert isinstance(result, CallToolResult) and not result.isError
    text, image = result.content
    assert isinstance(text, TextContent) and isinstance(image, ImageContent)
    assert image.mimeType == 'image/png' and base64.b64decode(image.data).startswith(b'\x89PNG')
    meta = json.loads(text.text)
    assert meta['width'] == 480 and 'data_base64' not in meta  # the bytes are only in the image part

    csv = tools['get_analysis_artifact'](job_id, 'summary.csv')
    assert not csv.isError and len(csv.content) == 1 and 'tuned,1.7' in json.loads(csv.content[0].text)['content']
    missing = tools['get_analysis_artifact'](job_id, '../job.json')
    assert missing.isError and json.loads(missing.content[0].text)['error_type'] == 'invalid_path'

    assert tools['delete_analysis_job'](job_id)['deleted'] is True
    assert tools['get_analysis_job'](job_id)['error_type'] == 'not_found'
    assert tools['cancel_analysis_job']('0' * 32)['error_type'] == 'not_found'


def test_the_real_mcp_server_returns_image_content(project, forward_to_api):
    server = mcp_server.create_mcp_server(0)
    schemas = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    assert {'run_analysis', 'get_analysis_job', 'get_analysis_artifact', 'cancel_analysis_job', 'delete_analysis_job',
            'get_session_results', 'get_live_sessions'} <= set(schemas)
    assert schemas['get_analysis_artifact'].outputSchema is None

    started = asyncio.run(server.call_tool('run_analysis', {'code': CHART_CODE, 'inputs': INPUTS}))
    contents = started[0] if isinstance(started, tuple) else started
    job_id = json.loads(contents[0].text)['job']['id']
    deadline = time.monotonic() + WAIT_SECONDS
    while analysis_jobs.get_job(job_id)['job']['status'] == 'running' and time.monotonic() < deadline:
        time.sleep(0.05)

    result = asyncio.run(server.call_tool('get_analysis_artifact', {'job_id': job_id, 'path': 'charts/equity.png'}))
    assert isinstance(result, CallToolResult)
    assert [type(c).__name__ for c in result.content] == ['TextContent', 'ImageContent']
    assert base64.b64decode(result.content[1].data).startswith(b'\x89PNG')


def test_artifact_result_turns_errors_into_tool_errors():
    error = artifact_result({'status': 'error', 'error_type': 'not_found', 'message': 'gone'})
    assert error.isError and json.loads(error.content[0].text)['error_type'] == 'not_found'


def test_policy_is_stated_for_agents_and_docs_do_not_need_it():
    rules = _load_packaged_rules()
    assert 'This authorizes a temporary analysis workspace only, not files in `research_scripts/`.' in rules
    assert 'never with a research script' in rules
    assert 'never start, stop, or change live trading' in rules
    mcp = FakeMCP()
    register_resources(mcp)
    guide = mcp.resources['jesse://session_analysis']()
    assert 'It is **not** a request for a' in guide and '**not\nsandboxed**' in guide
    assert '24 hours' in guide and 'inputs/<name>.json' in guide
    assert 'run_analysis' in mcp.resources['jesse://research_scripts']()
    register_tools(mcp)
    run_doc = mcp.tools['run_analysis'].__doc__
    assert 'NOT a request for a research script' in run_doc and 'NOT sandboxed' in run_doc
    assert 'run_analysis' in mcp_server.INSTRUCTIONS and 'jesse://session_analysis' in mcp_server.INSTRUCTIONS
