import errno
import io
import json
import os
import subprocess
import sys
import threading
import time
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import jesse.mcp.tools.services.project_files as project_files_service
from jesse.controllers import research_scripts_controller
from jesse.mcp.tools import register_tools
from jesse.services import auth, research_jobs
from tests.mcp_tool_adapters import callable_tool


PASSWORD = 'research-scripts-password'
HEADERS = {'Authorization': sha256(PASSWORD.encode('utf-8')).hexdigest()}
# Every job in this file is a tiny disposable script; none imports Jesse, touches the
# database or network, or trains anything. Jobs finish in well under this.
WAIT_SECONDS = 20


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = callable_tool(func)
            return func

        return decorator

    def resource(self, uri):
        return lambda func: func


@pytest.fixture
def project(tmp_path, monkeypatch) -> Path:
    # These workflows require no-follow directory descriptors and POSIX job cleanup.
    if os.name == 'nt':
        pytest.skip('Project-file and research workflows require Linux or macOS, including Docker.')
    root = tmp_path / 'project'
    (root / 'strategies' / 'MyStrategy').mkdir(parents=True)
    (root / 'strategies' / 'MyStrategy' / '__init__.py').write_text('VALUE = 42\n', encoding='utf-8')
    (root / 'storage').mkdir()
    (root / 'research_scripts').mkdir()
    monkeypatch.chdir(root)
    # Short grace periods keep cancellation tests fast; production values are asserted separately.
    monkeypatch.setattr(research_jobs, 'TERMINATE_GRACE_SECONDS', 1.0)
    monkeypatch.setattr(research_jobs, '_POLL_SECONDS', 0.05)
    yield root
    research_jobs.terminate_all_jobs()
    with research_jobs._jobs_lock:
        research_jobs._jobs.clear()


@pytest.fixture
def api(monkeypatch) -> TestClient:
    monkeypatch.setitem(auth.ENV_VALUES, 'PASSWORD', PASSWORD)
    app = FastAPI()

    @app.exception_handler(auth.InvalidAuthError)
    async def invalid_auth_handler(_request, _exc):
        return auth.unauthorized_response()

    app.include_router(research_scripts_controller.router)
    return TestClient(app)


def _script(project: Path, relative: str, source: str) -> str:
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding='utf-8')
    return relative


def _run(api: TestClient, path: str, args=None, timeout_minutes=None) -> dict:
    payload = {'path': path}
    if args is not None:
        payload['args'] = args
    if timeout_minutes is not None:
        payload['timeout_minutes'] = timeout_minutes
    response = api.post('/research-scripts/run', json=payload, headers=HEADERS)
    assert response.status_code == 200, response.text
    job = response.json()['job']
    assert job['status'] == 'running'
    return job


def _refused(response, status_code: int, error_type: str) -> dict:
    assert response.status_code == status_code, response.text
    body = response.json()
    assert (body['status'], body['error_type']) == ('error', error_type), body
    return body


def _status(api: TestClient, job_id: str) -> dict:
    response = api.post('/research-scripts/jobs', json={'job_id': job_id}, headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()['job']


def _wait(api: TestClient, job_id: str) -> dict:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        job = _status(api, job_id)
        if job['status'] != 'running':
            return job
        time.sleep(0.05)
    raise AssertionError(f'job {job_id} did not finish')


def _output(api: TestClient, job_id: str, tail_lines: int = 200) -> dict:
    response = api.post('/research-scripts/output', json={'job_id': job_id, 'tail_lines': tail_lines}, headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def _wait_for_file(path: Path) -> str:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        if path.exists() and path.read_text().strip():
            return path.read_text().strip()
        time.sleep(0.05)
    raise AssertionError(f'{path} was never written')


def _pid_gone(pid: int) -> bool:
    """True once the PID no longer exists (an orphan is reaped by init shortly after it exits)."""
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


# A script that starts a long-lived child in its own process group, records the child's PID,
# and then sleeps (or exits immediately), for checking that the whole group is stopped.
SPAWNER = '''
import subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
open(sys.argv[1], "w").write(str(child.pid))
print("spawned", flush=True)
if sys.argv[2] == "sleep":
    time.sleep(120)
'''


# ---------------------------------------------------------------------------
# Running scripts
# ---------------------------------------------------------------------------

def test_every_research_route_requires_authentication(project, api):
    for route in ('run', 'jobs', 'output', 'cancel'):
        response = api.post(f'/research-scripts/{route}', json={'path': 'research_scripts/a.py', 'job_id': 'a' * 32},
                            headers={'Authorization': 'wrong-token'})
        assert response.status_code == 401
    assert not (project / 'storage' / 'research-jobs').exists()


def test_script_runs_from_the_project_root_with_this_interpreter_and_literal_arguments(project, api):
    script = _script(project, 'research_scripts/deep/folder/probe.py', '''
import json, os, sys
import strategies.MyStrategy as strategy
print(json.dumps({
    "cwd": os.getcwd(),
    "executable": sys.executable,
    "argv": sys.argv,
    "strategy_value": strategy.VALUE,
    "stdin": sys.stdin.read(),
}))
''')
    tricky = ['$(touch pwned)', '; rm -rf strategies', '*', 'two words', "quote'\"", '']

    job = _run(api, script, tricky)
    finished = _wait(api, job['id'])

    assert finished['status'] == 'succeeded' and finished['exit_code'] == 0
    report = json.loads(_output(api, job['id'])['output'])
    assert os.path.realpath(report['cwd']) == os.path.realpath(project)
    assert report['executable'] == sys.executable
    assert report['argv'] == ['research_scripts/deep/folder/probe.py', *tricky]
    assert report['strategy_value'] == 42  # The project root is importable from any sub-folder.
    assert report['stdin'] == ''
    assert not (project / 'pwned').exists()
    assert (project / 'strategies' / 'MyStrategy' / '__init__.py').exists()


def test_job_record_and_log_are_stored_in_project_storage(project, api):
    job = _run(api, _script(project, 'research_scripts/ok.py', 'print("done")\n'), ['--x'])
    _wait(api, job['id'])

    record = json.loads((project / 'storage' / 'research-jobs' / f'{job["id"]}.json').read_text())
    assert record['script'] == 'research_scripts/ok.py' and record['args'] == ['--x']
    assert record['status'] == 'succeeded' and record['exit_code'] == 0
    assert record['started_at'] and record['finished_at']
    assert record['log_path'] == f'storage/logs/research-scripts/{job["id"]}.txt'
    assert (project / record['log_path']).read_text() == 'done\n'


def test_failures_report_exit_code_and_traceback_from_stderr(project, api):
    script = _script(project, 'research_scripts/fails.py', '''
import sys
print("before failure", flush=True)
print("warning on stderr", file=sys.stderr, flush=True)
if sys.argv[1] == "raise":
    raise ValueError("bad research input")
sys.exit(3)
''')

    raised = _wait(api, _run(api, script, ['raise'])['id'])
    exited = _wait(api, _run(api, script, ['exit'])['id'])

    assert (raised['status'], raised['exit_code']) == ('failed', 1)
    assert (exited['status'], exited['exit_code']) == ('failed', 3)
    output = _output(api, raised['id'])['output']
    assert 'before failure' in output and 'warning on stderr' in output
    assert 'ValueError: bad research input' in output


def test_cancel_stops_the_script_and_every_process_it_started(project, api):
    pid_file = project / 'child.pid'
    job = _run(api, _script(project, 'research_scripts/spawner.py', SPAWNER), [str(pid_file), 'sleep'])
    child_pid = int(_wait_for_file(pid_file))

    response = api.post('/research-scripts/cancel', json={'job_id': job['id']}, headers=HEADERS)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body['cancel_requested'] is True
    assert body['job']['status'] == 'cancelled'
    assert _pid_gone(job['pid'])
    assert _pid_gone(child_pid)
    assert _status(api, job['id'])['status'] == 'cancelled'

    again = api.post('/research-scripts/cancel', json={'job_id': job['id']}, headers=HEADERS).json()
    assert again['cancel_requested'] is False and again['job']['status'] == 'cancelled'


def test_processes_left_behind_by_a_finished_script_are_cleaned_up(project, api):
    pid_file = project / 'orphan.pid'
    job = _run(api, _script(project, 'research_scripts/leaves_child.py', SPAWNER), [str(pid_file), 'exit'])

    finished = _wait(api, job['id'])

    assert finished['status'] == 'succeeded'
    assert _pid_gone(int(_wait_for_file(pid_file)))


def test_a_script_that_ignores_sigterm_is_killed_after_the_grace_period(project, api):
    script = _script(project, 'research_scripts/stubborn.py', '''
import signal, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
print("ignoring SIGTERM", flush=True)
time.sleep(120)
''')
    job = _run(api, script)
    deadline = time.monotonic() + WAIT_SECONDS
    while 'ignoring' not in _output(api, job['id'])['output'] and time.monotonic() < deadline:
        time.sleep(0.05)

    body = api.post('/research-scripts/cancel', json={'job_id': job['id']}, headers=HEADERS).json()

    assert body['job']['status'] == 'cancelled'
    assert body['job']['exit_code'] == -9  # SIGKILL
    assert _pid_gone(job['pid'])


def test_deadline_stops_the_job_as_timed_out(project, api, monkeypatch):
    monkeypatch.setattr(research_jobs, '_deadline', lambda minutes: time.monotonic() + 0.5)
    pid_file = project / 'timeout.pid'

    job = _run(api, _script(project, 'research_scripts/slow.py', SPAWNER), [str(pid_file), 'sleep'], timeout_minutes=1)
    finished = _wait(api, job['id'])

    assert finished['status'] == 'timed_out'
    assert _pid_gone(int(_wait_for_file(pid_file)))


def test_concurrency_limit_refuses_extra_jobs_until_one_ends(project, api):
    sleeper = _script(project, 'research_scripts/sleeper.py', 'import time\ntime.sleep(120)\n')
    jobs = [_run(api, sleeper) for _ in range(research_jobs.MAX_CONCURRENT_JOBS)]

    body = _refused(api.post('/research-scripts/run', json={'path': sleeper}, headers=HEADERS), 429, 'too_many_jobs')
    assert str(research_jobs.MAX_CONCURRENT_JOBS) in body['message']

    api.post('/research-scripts/cancel', json={'job_id': jobs[0]['id']}, headers=HEADERS)
    assert _run(api, sleeper)['status'] == 'running'


def test_output_is_capped_on_disk_and_tail_reads_are_bounded(project, api, monkeypatch):
    monkeypatch.setattr(research_jobs, 'MAX_LOG_BYTES', 2000)
    script = _script(project, 'research_scripts/chatty.py', '''
for n in range(5000):
    print(f"line {n:05d}")
print("finished", flush=True)
''')

    job = _run(api, script)
    finished = _wait(api, job['id'])

    # The script was never blocked by the cap: it ran to completion.
    assert finished['status'] == 'succeeded' and finished['output_truncated'] is True
    log = (project / finished['log_path']).read_bytes()
    assert log.startswith(b'line 00000\n')
    assert b'output limit of' in log and len(log) < 2000 + 200
    assert b'finished' not in log

    tail = _output(api, job['id'], tail_lines=3)
    assert tail['lines_returned'] == 3 and tail['earlier_output_omitted'] is True
    assert tail['output_truncated'] is True and tail['job_status'] == 'succeeded'
    assert tail['output'].rstrip().endswith('further output was discarded]')


def test_tail_reads_only_the_end_of_large_logs(project, api, monkeypatch):
    monkeypatch.setattr(research_jobs, 'MAX_TAIL_BYTES', 64)
    job = _run(api, _script(project, 'research_scripts/many.py', 'for n in range(100):\n    print(f"row {n}")\n'))
    _wait(api, job['id'])

    tail = _output(api, job['id'], tail_lines=50)

    assert tail['earlier_output_omitted'] is True
    assert len(tail['output'].encode()) <= 64
    assert tail['output'].endswith('row 99\n')
    assert tail['output'].startswith('row ')  # The partial first line is dropped.


@pytest.mark.parametrize(('path', 'status_code', 'error_type'), [
    ('strategies/MyStrategy/__init__.py', 400, 'invalid_path'),
    ('research_scripts/notes.txt', 400, 'invalid_path'),
    ('research_scripts', 400, 'invalid_path'),
    ('/usr/bin/python3.py', 400, 'invalid_path'),
    ('research_scripts/../strategies/x.py', 400, 'invalid_path'),
    ('research_scripts/missing.py', 404, 'not_found'),
    ('research_scripts/folder.py', 409, 'wrong_type'),
])
def test_only_existing_python_files_in_research_scripts_can_run(project, api, path, status_code, error_type):
    (project / 'research_scripts' / 'notes.txt').write_text('print(1)')
    (project / 'research_scripts' / 'folder.py').mkdir()

    _refused(api.post('/research-scripts/run', json={'path': path}, headers=HEADERS), status_code, error_type)

    assert research_jobs._running_jobs() == []


def test_symlinked_scripts_and_script_folders_are_refused(project, api, tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'evil.py').write_text('open("pwned", "w").write("x")\n')
    try:
        (project / 'research_scripts' / 'link.py').symlink_to(outside / 'evil.py')
        (project / 'research_scripts' / 'linked_dir').symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('symlinks are not available on this platform')

    _refused(api.post('/research-scripts/run', json={'path': 'research_scripts/link.py'}, headers=HEADERS), 403, 'unsafe_path')
    _refused(api.post('/research-scripts/run', json={'path': 'research_scripts/linked_dir/evil.py'}, headers=HEADERS), 403, 'unsafe_path')

    assert research_jobs._running_jobs() == []
    assert not (project / 'pwned').exists()


@pytest.mark.parametrize('payload', [
    {'path': 'research_scripts/ok.py', 'timeout_minutes': 0},
    {'path': 'research_scripts/ok.py', 'timeout_minutes': research_jobs.MAX_TIMEOUT_MINUTES + 1},
    {'path': 'research_scripts/ok.py', 'args': ['x'] * (research_jobs.MAX_ARGS + 1)},
    {'path': 'research_scripts/ok.py', 'args': ['x' * (research_jobs.MAX_ARG_LENGTH + 1)]},
    {'path': 'research_scripts/ok.py', 'args': ['nul\x00byte']},
])
def test_run_limits_are_validated_before_starting(project, api, payload):
    _script(project, 'research_scripts/ok.py', 'print(1)\n')

    _refused(api.post('/research-scripts/run', json=payload, headers=HEADERS), 400, 'invalid_request')

    assert research_jobs._running_jobs() == []


def test_non_string_arguments_are_rejected_by_the_route_and_the_service(project, api):
    _script(project, 'research_scripts/ok.py', 'print(1)\n')

    response = api.post('/research-scripts/run', json={'path': 'research_scripts/ok.py', 'args': 'a b'}, headers=HEADERS)
    assert response.status_code == 422
    with pytest.raises(research_jobs.ProjectFileError) as refused:
        research_jobs.start_job('research_scripts/ok.py', [1, 2])  # type: ignore[list-item]
    assert refused.value.error_type == 'invalid_request'


@pytest.mark.parametrize('job_id', ['../../.env', 'x' * 32, '', 'A' * 32])
def test_job_ids_are_validated_before_touching_storage(project, api, job_id):
    for route in ('output', 'cancel'):
        body = api.post(f'/research-scripts/{route}', json={'job_id': job_id, 'tail_lines': 10}, headers=HEADERS).json()
        assert body['error_type'] == 'invalid_request'
    if job_id:
        assert api.post('/research-scripts/jobs', json={'job_id': job_id}, headers=HEADERS).json()['error_type'] == 'invalid_request'


def test_unknown_jobs_and_output_bounds(project, api):
    _refused(api.post('/research-scripts/jobs', json={'job_id': 'a' * 32}, headers=HEADERS), 404, 'not_found')
    job = _run(api, _script(project, 'research_scripts/ok.py', 'print(1)\n'))
    _wait(api, job['id'])
    for tail_lines in (0, research_jobs.MAX_TAIL_LINES + 1):
        _refused(api.post('/research-scripts/output', json={'job_id': job['id'], 'tail_lines': tail_lines}, headers=HEADERS),
                 400, 'invalid_request')


def test_status_is_still_answered_when_the_final_record_cannot_be_saved(project, api, monkeypatch):
    real_write = research_jobs._write_record

    def fail_final_write(record):
        if record['status'] != 'running':
            raise OSError(28, 'No space left on device')
        real_write(record)

    monkeypatch.setattr(research_jobs, '_write_record', fail_final_write)
    job = _run(api, _script(project, 'research_scripts/ok.py', 'print(1)\n'))

    finished = _wait(api, job['id'])

    assert finished['status'] == 'succeeded' and finished['exit_code'] == 0
    assert research_jobs._running_jobs() == []  # Finished jobs never count toward the limit.


def test_job_left_running_by_a_previous_jesse_process_is_reported_interrupted(project, api):
    job_id = 'b' * 32
    jobs_dir = project / 'storage' / 'research-jobs'
    jobs_dir.mkdir(parents=True)
    (jobs_dir / f'{job_id}.json').write_text(json.dumps({
        'id': job_id, 'script': 'research_scripts/old.py', 'args': [], 'status': 'running', 'pid': 999999,
        'exit_code': None, 'started_at': '2026-09-01T00:00:00+00:00', 'finished_at': None,
    }))

    job = _status(api, job_id)

    assert job['status'] == 'interrupted' and 'no longer tracked' in job['message']
    assert json.loads((jobs_dir / f'{job_id}.json').read_text())['status'] == 'interrupted'
    cancel = api.post('/research-scripts/cancel', json={'job_id': job_id}, headers=HEADERS).json()
    assert cancel['cancel_requested'] is False


def test_listing_returns_newest_jobs_first(project, api):
    first = _run(api, _script(project, 'research_scripts/a.py', 'print("a")\n'))
    _wait(api, first['id'])
    time.sleep(1.1)  # started_at has one-second resolution
    second = _run(api, _script(project, 'research_scripts/b.py', 'print("b")\n'))
    _wait(api, second['id'])

    response = api.post('/research-scripts/jobs', json={}, headers=HEADERS)

    assert [job['id'] for job in response.json()['jobs']] == [second['id'], first['id']]


def test_shutdown_stops_running_jobs_and_marks_them_interrupted(project, api):
    pid_file = project / 'shutdown.pid'
    job = _run(api, _script(project, 'research_scripts/spawner.py', SPAWNER), [str(pid_file), 'sleep'])
    child_pid = int(_wait_for_file(pid_file))

    research_jobs.terminate_all_jobs()

    # regression: the final record is on disk before shutdown returns, not written afterwards.
    record = json.loads((project / 'storage' / 'research-jobs' / f"{job['id']}.json").read_text())
    assert record['status'] == 'interrupted' and record['finished_at']
    assert _pid_gone(job['pid']) and _pid_gone(child_pid)
    assert _wait(api, job['id'])['status'] == 'interrupted'


def test_production_limits_match_the_documented_values():
    assert research_jobs.MAX_CONCURRENT_JOBS == 2
    assert (research_jobs.DEFAULT_TIMEOUT_MINUTES, research_jobs.MAX_TIMEOUT_MINUTES) == (60, 720)
    assert research_jobs.MAX_LOG_BYTES == 20 * 1024 * 1024
    assert research_jobs.MAX_TAIL_BYTES == 256 * 1024
    assert research_jobs.TERMINATE_GRACE_SECONDS == 5.0


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------

@pytest.fixture
def tools(api, monkeypatch):
    """The registered MCP tools, with their HTTP calls served by the real router in-process."""
    def forward_post(url, json=None, headers=None, timeout=None):
        return api.post(url.removeprefix('http://jesse.test'), json=json, headers=headers)

    monkeypatch.setattr(project_files_service.mcp_config, 'JESSE_API_URL', 'http://jesse.test')
    monkeypatch.setattr(project_files_service.mcp_config, 'JESSE_PASSWORD', PASSWORD)
    monkeypatch.setattr(project_files_service.requests, 'post', forward_post)
    mcp = FakeMCP()
    register_tools(mcp)
    return mcp.tools


def test_mcp_research_tools_run_poll_read_and_cancel(project, tools):
    _script(project, 'research_scripts/hello.py', 'import sys\nprint("hello", *sys.argv[1:])\n')
    _script(project, 'research_scripts/sleeper.py', 'import time\ntime.sleep(120)\n')

    started = tools['run_research_script']('research_scripts/hello.py', ['a b', 'c'])
    assert started['status'] == 'success' and started['action'] == 'run_research_script'
    job_id = started['job']['id']
    deadline = time.monotonic() + WAIT_SECONDS
    while tools['get_research_job_status'](job_id)['job']['status'] == 'running' and time.monotonic() < deadline:
        time.sleep(0.05)
    assert tools['get_research_job_status'](job_id)['job']['status'] == 'succeeded'
    output = tools['get_research_job_output'](job_id)
    assert output['status'] == 'success' and output['job_status'] == 'succeeded'
    assert output['output'] == 'hello a b c\n'
    assert job_id in [job['id'] for job in tools['get_research_job_status']()['jobs']]

    sleeper = tools['run_research_script']('research_scripts/sleeper.py')['job']['id']
    cancelled = tools['cancel_research_job'](sleeper)
    assert cancelled['status'] == 'success' and cancelled['job']['status'] == 'cancelled'

    refused = tools['run_research_script']('strategies/MyStrategy/__init__.py')
    assert (refused['status'], refused['error_type']) == ('error', 'invalid_path')


# ---------------------------------------------------------------------------
# Shared job engine lifecycle
# ---------------------------------------------------------------------------

# Exits 0 right away, leaving a child that ignores SIGTERM, so Jesse's cleanup of the group
# (SIGTERM, then SIGKILL after the grace period) is still running when a cancel arrives.
EXIT_WITH_STUBBORN_CHILD = '''
import os, subprocess, sys, time
pid_file = sys.argv[1]
child = subprocess.Popen([sys.executable, "-c",
    "import signal, sys, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
    "open(sys.argv[1], 'w').write('ready'); time.sleep(120)", pid_file + ".ready"])
while not os.path.exists(pid_file + ".ready"):
    time.sleep(0.01)
open(pid_file, "w").write(str(child.pid))
'''


def test_a_cancel_after_the_script_exited_does_not_relabel_its_result(project, api):
    pid_file = project / 'stubborn.pid'
    job = _run(api, _script(project, 'research_scripts/stubborn.py', EXIT_WITH_STUBBORN_CHILD), [str(pid_file)])
    child_pid = int(_wait_for_file(pid_file))
    assert _pid_gone(job['pid'])  # the script itself has exited; its child is being cleaned up

    cancel = api.post('/research-scripts/cancel', json={'job_id': job['id']}, headers=HEADERS).json()

    assert cancel['cancel_requested'] is False
    assert cancel['job']['status'] == 'succeeded' and cancel['job']['exit_code'] == 0
    assert _pid_gone(child_pid)  # the leftover child was still stopped


@pytest.mark.skipif(os.name == 'nt', reason='Research process-group cleanup requires POSIX killpg.')
def test_a_process_group_is_never_signalled_again_once_it_is_gone(monkeypatch):
    calls = []

    def killpg(pgid, sig):
        calls.append((pgid, sig))
        raise ProcessLookupError()

    monkeypatch.setattr(research_jobs.os, 'killpg', killpg)
    job = research_jobs._Job(research_jobs.RESEARCH, {'id': 'x'}, SimpleNamespace(pid=424242))

    with job.lock:
        assert job.signal_group(0) is False
        assert job.signal_group(9) is False
    job.kill_now()

    # Once no member is left the ID may belong to someone else, so it is signalled only once.
    assert calls == [(424242, 0)] and job.group_gone is True


def test_old_research_job_records_and_logs_are_pruned(project, api, monkeypatch):
    monkeypatch.setattr(research_jobs, 'MAX_KEPT_RESEARCH_JOBS', 2)
    jobs_dir, logs_dir = project / 'storage' / 'research-jobs', project / 'storage' / 'logs' / 'research-scripts'
    jobs_dir.mkdir(parents=True)
    logs_dir.mkdir(parents=True)
    old_ids = [f'{i:032x}' for i in range(1, 5)]
    for age, job_id in enumerate(old_ids):  # old_ids[0] is the newest
        (jobs_dir / f'{job_id}.json').write_text(json.dumps({'id': job_id, 'status': 'succeeded'}))
        (logs_dir / f'{job_id}.txt').write_text('log')
        stamp = time.time() - 1000 - age * 100
        os.utime(jobs_dir / f'{job_id}.json', (stamp, stamp))

    job = _run(api, _script(project, 'research_scripts/ok.py', 'print(1)\n'))
    _wait(api, job['id'])

    kept = {path.stem for path in jobs_dir.glob('*.json')}
    assert kept == {old_ids[0], old_ids[1], job['id']}
    assert {path.stem for path in logs_dir.glob('*.txt')} == kept


class _FullDiskLog(io.RawIOBase):
    """A job log on a full disk: every write fails the way a real one does (ENOSPC)."""

    def writable(self):
        return True

    def write(self, data):
        raise OSError(errno.ENOSPC, 'No space left on device')


def test_output_is_still_drained_when_the_log_cannot_be_written(project):
    # Far more than a pipe buffer, so the script blocks for good unless the pump keeps reading.
    process = subprocess.Popen(
        [sys.executable, '-c', 'import sys; sys.stdout.write("x" * (4 * 1024 * 1024))'],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    job = research_jobs._Job(research_jobs.RESEARCH, {'id': 'a' * 32}, process)
    pump = threading.Thread(target=research_jobs._pump_output, args=(job, _FullDiskLog(), 1024 ** 3))
    pump.start()
    try:
        assert process.wait(timeout=WAIT_SECONDS) == 0
        pump.join(timeout=WAIT_SECONDS)
        assert not pump.is_alive() and job.output_truncated is True
    finally:
        process.kill()
        process.wait()
