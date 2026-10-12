import os
import shutil
from hashlib import sha256
from pathlib import Path

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

import jesse.mcp.tools.services.strategy as strategy_service
from jesse.controllers import strategy_controller
from jesse.mcp.agent_rules import _load_packaged_rules
from jesse.mcp.resources import register_resources
from jesse.mcp.tools import register_tools
from jesse.services import auth
from jesse.services.nofollow_fs import extended_path
from tests.mcp_tool_adapters import callable_tool


PASSWORD = 'strategy-reports-password'
AUTHORIZATION = sha256(PASSWORD.encode('utf-8')).hexdigest()
STRATEGY_CODE = 'from jesse.strategies import Strategy\n\n\nclass MyStrategy(Strategy):\n    pass\n'
REPORT = '# MyStrategy report\n\nDashboard: http://localhost:9000/backtest/abc\r\nSharpe — 1.42 ✅\n'


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


@pytest.fixture
def project(tmp_path, monkeypatch) -> Path:
    """A disposable Jesse project; the handler resolves strategies/ from the working directory."""
    monkeypatch.chdir(tmp_path)
    strategy = tmp_path / 'strategies' / 'MyStrategy'
    strategy.mkdir(parents=True)
    (strategy / '__init__.py').write_text(STRATEGY_CODE, encoding='utf-8')
    return tmp_path


@pytest.fixture
def api_client(monkeypatch) -> TestClient:
    """The real strategy router with production authentication and error shape."""
    monkeypatch.setitem(auth.ENV_VALUES, 'PASSWORD', PASSWORD)
    app = FastAPI()

    @app.exception_handler(auth.InvalidAuthError)
    async def invalid_auth_handler(_request, _exc):
        return auth.unauthorized_response()

    app.include_router(strategy_controller.router)
    return TestClient(app)


@pytest.fixture
def report_tool(api_client, monkeypatch):
    """The registered MCP tool, with its HTTP calls served by the real router in-process."""
    def forward_post(url, json=None, headers=None, timeout=None):
        assert url.startswith('http://jesse.test/')
        return api_client.post(url.removeprefix('http://jesse.test'), json=json, headers=headers)

    monkeypatch.setattr(strategy_service.mcp_config, 'JESSE_API_URL', 'http://jesse.test')
    monkeypatch.setattr(strategy_service.mcp_config, 'JESSE_PASSWORD', PASSWORD)
    monkeypatch.setattr(strategy_service.requests, 'post', forward_post)
    mcp = FakeMCP()
    register_tools(mcp)
    return mcp.tools['save_strategy_report']


def _save(client: TestClient, name='MyStrategy', filename='report.md', content=REPORT, overwrite=None, headers=None):
    payload = {'name': name, 'filename': filename, 'content': content}
    if overwrite is not None:
        payload['overwrite'] = overwrite
    return client.post(
        '/strategy/save-report',
        json=payload,
        headers={'Authorization': AUTHORIZATION} if headers is None else headers,
    )


def _snapshot(root: Path) -> dict:
    """Every path under root with its link target or file bytes, to prove a request wrote nothing."""
    entries = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for entry in dirnames + filenames:
            path = Path(dirpath) / entry
            if path.is_symlink():
                entries[str(path)] = ('link', os.readlink(path))
            elif path.is_file():
                entries[str(path)] = ('file', path.read_bytes())
            else:
                entries[str(path)] = ('dir', None)
    return entries


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError):
        pytest.skip('symlinks are not available on this platform')


def test_saving_a_report_requires_authentication(project, api_client):
    before = _snapshot(project)

    response = _save(api_client, headers={'Authorization': 'wrong-token'})

    assert response.status_code == 401
    assert _snapshot(project) == before


def test_report_is_saved_verbatim_in_a_newly_created_reports_folder(project, api_client):
    reports = project / 'strategies' / 'MyStrategy' / 'reports'
    assert not reports.exists()

    response = _save(api_client, filename='BTCUSDT_sharpe_optimization_report.md')

    assert response.status_code == 200
    assert response.json() == {
        'status': 'success',
        'message': 'Report saved to strategies/MyStrategy/reports/BTCUSDT_sharpe_optimization_report.md in the Jesse project.',
        'path': 'strategies/MyStrategy/reports/BTCUSDT_sharpe_optimization_report.md',
        'overwritten': False,
        'size_bytes': len(REPORT.encode('utf-8')),
    }
    # Stored byte-for-byte: UTF-8, and the CRLF inside the content is not translated.
    assert (reports / 'BTCUSDT_sharpe_optimization_report.md').read_bytes() == REPORT.encode('utf-8')
    assert (project / 'strategies' / 'MyStrategy' / '__init__.py').read_text(encoding='utf-8') == STRATEGY_CODE


def test_existing_report_is_replaced_only_with_explicit_overwrite(project, api_client):
    reports = project / 'strategies' / 'MyStrategy' / 'reports'
    assert _save(api_client, content='# first\n').status_code == 200

    refused = _save(api_client, content='# second\n')
    refused_explicitly = _save(api_client, content='# second\n', overwrite=False)

    for response in (refused, refused_explicitly):
        assert response.status_code == 409
        assert 'already exists' in response.json()['message']
        assert 'overwrite=true' in response.json()['message']
    assert (reports / 'report.md').read_text(encoding='utf-8') == '# first\n'

    replaced = _save(api_client, content='# second\n', overwrite=True)

    assert replaced.status_code == 200
    assert replaced.json()['overwritten'] is True
    assert (reports / 'report.md').read_text(encoding='utf-8') == '# second\n'
    # The temporary file used for the atomic replace is gone.
    assert sorted(os.listdir(reports)) == ['report.md']


def test_report_created_concurrently_after_the_checks_is_not_clobbered(project, api_client, monkeypatch):
    reports = project / 'strategies' / 'MyStrategy' / 'reports'
    real_mkdir = os.mkdir

    def mkdir_then_competing_save(path, *args, **kwargs):
        # Simulates another save landing between save_report's existence check and its write.
        real_mkdir(path, *args, **kwargs)
        (reports / 'report.md').write_text('# competing save\n', encoding='utf-8')

    monkeypatch.setattr(os, 'mkdir', mkdir_then_competing_save)

    response = _save(api_client)

    assert response.status_code == 409
    assert (reports / 'report.md').read_text(encoding='utf-8') == '# competing save\n'


def test_strategy_deleted_during_a_save_is_not_recreated(project, api_client, monkeypatch):
    strategy = project / 'strategies' / 'MyStrategy'
    real_isdir = os.path.isdir
    # Match the path form the handler uses, including the extended Windows prefix.
    expected_path = extended_path('strategies/MyStrategy')

    def isdir_then_delete_strategy(path):
        # Simulates the strategy being deleted right after save_report confirmed it exists.
        result = real_isdir(path)
        if path == expected_path:
            shutil.rmtree(strategy)
        return result

    monkeypatch.setattr(os.path, 'isdir', isdir_then_delete_strategy)

    response = _save(api_client)

    assert response.status_code == 500
    assert not strategy.exists()


def test_overwrite_creates_a_missing_report(project, api_client):
    response = _save(api_client, overwrite=True)

    assert response.status_code == 200
    assert response.json()['overwritten'] is False
    assert (project / 'strategies' / 'MyStrategy' / 'reports' / 'report.md').read_bytes() == REPORT.encode('utf-8')


def test_longest_allowed_file_name_can_be_created_and_overwritten(project, api_client):
    # The overwrite path writes a longer temporary name first, which must still fit the filesystem.
    filename = 'r' * 197 + '.md'

    assert _save(api_client, filename=filename).status_code == 200
    assert _save(api_client, filename=filename, content='# updated\n', overwrite=True).status_code == 200
    # Read through the extended form: the absolute path is past Windows' 260-character limit.
    saved = project / 'strategies' / 'MyStrategy' / 'reports' / filename
    with open(extended_path(str(saved)), encoding='utf-8') as f:
        assert f.read() == '# updated\n'


def test_report_for_a_missing_strategy_is_rejected_without_creating_folders(project, api_client):
    before = _snapshot(project)

    response = _save(api_client, name='GhostStrategy')

    assert response.status_code == 404
    assert response.json()['message'] == 'Strategy "GhostStrategy" does not exist.'
    assert _snapshot(project) == before


@pytest.mark.parametrize(
    'filename',
    [
        '../escape.md',
        '../../escape.md',
        'nested/report.md',
        'nested\\report.md',
        '..\\escape.md',
        '/tmp/escape.md',
        'C:\\escape.md',
        '__init__.py',
        'report.txt',
        'report.md.py',
        'report.MD',
        'report',
        '.md',
        '.hidden.md',
        ' report.md',
        'my report.md',
        'report.md\n',
        'report\x00.md',
        '',
        'r' * 198 + '.md',
    ],
)
def test_unsafe_or_non_markdown_file_names_are_rejected(project, api_client, filename):
    before = _snapshot(project)

    response = _save(api_client, filename=filename, overwrite=True)

    assert response.status_code == 400
    assert 'Invalid report file name' in response.json()['message']
    assert _snapshot(project) == before


@pytest.mark.parametrize(
    'name',
    ['', '.', '..', '../MyStrategy', 'MyStrategy/..', 'MyStrategy/reports', '/abs', 'C:\\MyStrategy', 'My Strategy'],
)
def test_strategy_names_that_could_leave_strategies_folder_are_rejected(project, api_client, name):
    before = _snapshot(project)

    response = _save(api_client, name=name, overwrite=True)

    assert response.status_code == 400
    assert 'Invalid strategy name' in response.json()['message']
    assert _snapshot(project) == before


def test_empty_report_content_is_rejected(project, api_client):
    before = _snapshot(project)

    response = _save(api_client, content='  \n\t')

    assert response.status_code == 400
    assert response.json()['message'] == 'Report content is empty.'
    assert _snapshot(project) == before


def test_symlinked_reports_folder_is_refused(project, api_client, tmp_path_factory):
    outside = tmp_path_factory.mktemp('outside')
    _symlink_or_skip(project / 'strategies' / 'MyStrategy' / 'reports', outside)

    for overwrite in (False, True):
        response = _save(api_client, overwrite=overwrite)

        assert response.status_code == 403
        assert 'symlink' in response.json()['message']
    assert list(outside.iterdir()) == []


def test_symlinked_report_file_is_never_written_through(project, api_client, tmp_path_factory):
    outside = tmp_path_factory.mktemp('outside') / 'config.py'
    outside.write_text('SECRET = 1\n', encoding='utf-8')
    reports = project / 'strategies' / 'MyStrategy' / 'reports'
    reports.mkdir()
    _symlink_or_skip(reports / 'report.md', outside)

    for overwrite in (False, True):
        response = _save(api_client, overwrite=overwrite)

        assert response.status_code == 403
    assert outside.read_text(encoding='utf-8') == 'SECRET = 1\n'
    assert (reports / 'report.md').is_symlink()


def test_non_regular_reports_folder_or_report_is_refused(project, api_client):
    strategy = project / 'strategies' / 'MyStrategy'
    (strategy / 'reports').write_text('not a folder', encoding='utf-8')

    assert _save(api_client).status_code == 403
    assert (strategy / 'reports').read_text(encoding='utf-8') == 'not a folder'

    (strategy / 'reports').unlink()
    (strategy / 'reports' / 'report.md').mkdir(parents=True)

    assert _save(api_client, overwrite=True).status_code == 403
    assert (strategy / 'reports' / 'report.md').is_dir()


def test_symlinked_strategy_folder_is_followed_like_strategy_loading(project, api_client, tmp_path_factory):
    shared = tmp_path_factory.mktemp('shared') / 'LinkedStrategy'
    shared.mkdir()
    (shared / '__init__.py').write_text(STRATEGY_CODE, encoding='utf-8')
    _symlink_or_skip(project / 'strategies' / 'LinkedStrategy', shared)

    response = _save(api_client, name='LinkedStrategy')

    assert response.status_code == 200
    assert response.json()['path'] == 'strategies/LinkedStrategy/reports/report.md'
    assert (shared / 'reports' / 'report.md').read_bytes() == REPORT.encode('utf-8')


def test_mcp_tool_saves_on_the_jesse_host_through_the_api(project, report_tool):
    saved = report_tool('MyStrategy', 'BTCUSDT_sharpe_optimization_report.md', REPORT)

    assert saved == {
        'status': 'success',
        'action': 'strategy_report_saved',
        'strategy_name': 'MyStrategy',
        'filename': 'BTCUSDT_sharpe_optimization_report.md',
        'path': 'strategies/MyStrategy/reports/BTCUSDT_sharpe_optimization_report.md',
        'overwritten': False,
        'size_bytes': len(REPORT.encode('utf-8')),
        'location': strategy_service.REPORT_LOCATION,
        'message': 'Report saved to strategies/MyStrategy/reports/BTCUSDT_sharpe_optimization_report.md in the Jesse project.',
    }
    assert (project / saved['path']).read_bytes() == REPORT.encode('utf-8')
    assert 'not in the assistant' in saved['location']


def test_mcp_tool_maps_every_refusal_to_a_stable_error_type(project, report_tool, tmp_path_factory):
    assert report_tool('MyStrategy', 'report.md', '# first\n')['status'] == 'success'

    exists = report_tool('MyStrategy', 'report.md', '# second\n')
    assert exists['status'] == 'error'
    assert exists['action'] == 'strategy_report_save_failed'
    assert exists['error_type'] == 'report_exists'
    assert 'overwrite=true' in exists['message']

    replaced = report_tool('MyStrategy', 'report.md', '# second\n', overwrite=True)
    assert replaced['status'] == 'success'
    assert replaced['overwritten'] is True

    assert report_tool('MyStrategy', '../escape.md', REPORT)['error_type'] == 'invalid_request'
    assert report_tool('../MyStrategy', 'report.md', REPORT)['error_type'] == 'invalid_request'
    assert report_tool('GhostStrategy', 'report.md', REPORT)['error_type'] == 'strategy_not_found'

    other = project / 'strategies' / 'Other'
    other.mkdir()
    _symlink_or_skip(other / 'reports', tmp_path_factory.mktemp('outside'))
    assert report_tool('Other', 'report.md', REPORT)['error_type'] == 'unsafe_report_path'

    assert (project / 'strategies' / 'MyStrategy' / 'reports' / 'report.md').read_text(encoding='utf-8') == '# second\n'
    assert not (project / 'strategies' / 'escape.md').exists()


def test_mcp_tool_reports_authentication_and_connection_failures(project, report_tool, monkeypatch):
    monkeypatch.setattr(strategy_service.mcp_config, 'JESSE_PASSWORD', 'wrong-password')
    assert report_tool('MyStrategy', 'report.md', REPORT)['error_type'] == 'authentication_failed'

    def unreachable(*args, **kwargs):
        raise requests.exceptions.ConnectionError('connection refused')

    monkeypatch.setattr(strategy_service.requests, 'post', unreachable)
    failure = report_tool('MyStrategy', 'report.md', REPORT)

    assert failure['error_type'] == 'connection_error'
    assert failure['details'] == 'connection refused'
    assert not (project / 'strategies' / 'MyStrategy' / 'reports').exists()


def test_report_tool_is_registered_and_documented():
    mcp = FakeMCP()

    register_tools(mcp)

    docs = mcp.tools['save_strategy_report'].__doc__
    assert docs is not None
    assert 'machine running Jesse' in docs
    assert 'strategies/<strategy_name>/reports/<filename>' in docs
    assert 'report_exists' in docs
    # Projects keep their synced rules until the Jesse version changes, so the tool itself
    # must override the older rule text that said to write reports with local file tools.
    assert 'supersedes older Jesse agent rules' in docs


def test_agent_rules_and_guides_send_reports_through_the_tool():
    rules = _load_packaged_rules()

    assert 'save_strategy_report' in rules
    assert 'Never create, edit, or verify reports with your own file-editing or filesystem tools' in rules
    assert 'strategies/<StrategyName>/reports/<REPORT_FILENAME>.md' in rules
    # The superseded guidance told assistants to write reports with their own file tools.
    assert 'Report-only exception' not in rules
    assert "normal workspace" not in rules
    assert 'Do not search for, request, or wait for a Jesse MCP report-writing tool' not in rules

    mcp = FakeMCP()
    register_resources(mcp)
    assert '### save_strategy_report()' in mcp.resources['jesse://backtest_management']()
    assert 'save_strategy_report(' in mcp.resources['jesse://optimization']()
