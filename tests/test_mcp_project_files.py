import asyncio
import errno
import json
import os
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import jesse.mcp.tools.services.project_files as project_files_service
from jesse.controllers import project_files_controller, research_scripts_controller, strategy_controller
from jesse.mcp import server as mcp_server
from jesse.mcp.agent_rules import _load_packaged_rules
from jesse.mcp.resources import register_resources
from jesse.mcp.tools import register_tools
from jesse.services import auth, project_files
from tests.mcp_tool_adapters import callable_tool


PASSWORD = 'project-files-password'
AUTHORIZATION = sha256(PASSWORD.encode('utf-8')).hexdigest()
HEADERS = {'Authorization': AUTHORIZATION}
# No jesse import, so nothing here depends on a configured Jesse project.
STRATEGY_CODE = 'class MyStrategy:\n    pass\n'
MODEL_BYTES = b'\x80\x04\x95model\x00\xff\xfe binary pickle-like bytes'

FILE_TOOLS = {
    'list_project_files', 'read_project_file', 'write_project_file', 'create_project_directory',
    'move_project_path', 'copy_project_path', 'delete_project_path',
}
RESEARCH_TOOLS = {'run_research_script', 'get_research_job_status', 'get_research_job_output', 'cancel_research_job'}


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
    """A disposable Jesse project; the file service resolves both roots from the working directory."""
    root = tmp_path / 'project'
    strategy = root / 'strategies' / 'MyStrategy'
    strategy.mkdir(parents=True)
    (root / 'storage').mkdir()
    (strategy / '__init__.py').write_text(STRATEGY_CODE, encoding='utf-8')
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def outside(tmp_path) -> Path:
    """A folder outside the project that no request may read or change."""
    folder = tmp_path / 'outside'
    folder.mkdir()
    (folder / 'secret.txt').write_text('SECRET=outside\n', encoding='utf-8')
    (folder / '__init__.py').write_text('class Outside:\n    pass\n', encoding='utf-8')
    return folder


@pytest.fixture
def api(monkeypatch) -> TestClient:
    """The real routers with production authentication and error shape."""
    monkeypatch.setitem(auth.ENV_VALUES, 'PASSWORD', PASSWORD)
    app = FastAPI()

    @app.exception_handler(auth.InvalidAuthError)
    async def invalid_auth_handler(_request, _exc):
        return auth.unauthorized_response()

    app.include_router(project_files_controller.router)
    app.include_router(research_scripts_controller.router)
    app.include_router(strategy_controller.router)
    return TestClient(app)


def _post(api: TestClient, route: str, payload: dict):
    return api.post(f'/project-files/{route}', json=payload, headers=HEADERS)


def _ok(response) -> dict:
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == 'success'
    return body


def _refused(response, status_code: int, error_type: str) -> dict:
    assert response.status_code == status_code, response.text
    body = response.json()
    assert body['status'] == 'error'
    assert body['error_type'] == error_type, body
    return body


def _snapshot(root: Path) -> dict:
    """Every path under root with its link target or file bytes, to prove a request changed nothing."""
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


def _temp_leftovers(root: Path) -> list:
    return [path for path in root.rglob('.jesse-*')]


# ---------------------------------------------------------------------------
# Authentication and path validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('route', ['list', 'read', 'write', 'mkdir', 'move', 'copy', 'delete'])
def test_every_file_route_requires_authentication(project, api, route):
    before = _snapshot(project)
    payload = {'path': 'research_scripts/x.py', 'content': 'x', 'source': 'research_scripts/a', 'destination': 'research_scripts/b'}

    response = api.post(f'/project-files/{route}', json=payload, headers={'Authorization': 'wrong-token'})

    assert response.status_code == 401
    assert _snapshot(project) == before


@pytest.mark.parametrize('path', [
    '/etc/passwd',
    '~/secrets.txt',
    'C:/Windows/win.ini',
    '../outside/secret.txt',
    'strategies/../.env',
    'research_scripts/../.env',
    'research_scripts/./x.py',
    '.env',
    'storage/logs/x.txt',
    'strategies\\MyStrategy\\__init__.py',
    'research_scripts/x\x00.py',
    'jesse_strategies/x.py',
])
def test_paths_outside_the_two_roots_are_refused_without_side_effects(project, api, path):
    (project / '.env').write_text('PASSWORD=secret\n', encoding='utf-8')
    before = _snapshot(project)

    for route, payload in [
        ('read', {'path': path}),
        ('list', {'path': path}),
        ('write', {'path': path, 'content': 'owned'}),
        ('mkdir', {'path': path}),
        ('delete', {'path': path, 'recursive': True}),
        ('copy', {'source': path, 'destination': 'research_scripts/copied'}),
        ('copy', {'source': 'strategies/MyStrategy/__init__.py', 'destination': path}),
        ('move', {'source': path, 'destination': 'research_scripts/moved'}),
    ]:
        body = _refused(_post(api, route, payload), 400, 'invalid_path')
        assert 'secret' not in body['message'].lower() or 'secrets.txt' in path

    assert _snapshot(project) == before


def test_top_level_listing_shows_roots_without_creating_research_scripts(project, api):
    body = _ok(_post(api, 'list', {'path': ''}))

    assert body['entries'] == [
        {'path': 'strategies', 'type': 'directory'},
        {'path': 'research_scripts', 'type': 'missing'},
    ]
    assert not (project / 'research_scripts').exists()
    _refused(_post(api, 'list', {'path': 'research_scripts'}), 404, 'not_found')


# ---------------------------------------------------------------------------
# Symlink confinement
# ---------------------------------------------------------------------------

def test_symlinked_strategy_folder_is_never_followed_by_file_tools(project, api, outside):
    _symlink_or_skip(project / 'strategies' / 'Linked', outside)
    before_outside = _snapshot(outside)

    listing = _ok(_post(api, 'list', {'path': 'strategies', 'recursive': True}))
    linked = [entry for entry in listing['entries'] if entry['path'] == 'strategies/Linked']
    assert linked == [{'path': 'strategies/Linked', 'type': 'symlink', 'modified_at': linked[0]['modified_at']}]
    assert not any(entry['path'].startswith('strategies/Linked/') for entry in listing['entries'])

    for route, payload in [
        ('read', {'path': 'strategies/Linked/secret.txt'}),
        ('list', {'path': 'strategies/Linked'}),
        ('write', {'path': 'strategies/Linked/owned.py', 'content': 'owned'}),
        ('write', {'path': 'strategies/Linked/__init__.py', 'content': 'owned', 'overwrite': True}),
        ('mkdir', {'path': 'strategies/Linked/sub'}),
        ('delete', {'path': 'strategies/Linked/secret.txt'}),
        ('copy', {'source': 'strategies/Linked/secret.txt', 'destination': 'research_scripts/stolen.txt'}),
        ('copy', {'source': 'research_scripts', 'destination': 'strategies/Linked/copied'}),
        ('move', {'source': 'strategies/Linked/secret.txt', 'destination': 'research_scripts/stolen.txt'}),
    ]:
        response = _post(api, route, payload)
        assert response.status_code in (400, 403), (route, payload, response.text)
        assert response.json()['error_type'] in ('unsafe_path', 'invalid_request'), response.text
        assert 'SECRET' not in response.text

    assert _snapshot(outside) == before_outside
    assert not (project / 'research_scripts' / 'stolen.txt').exists()


def test_existing_strategy_tools_still_follow_symlinked_strategy_folders(project, api, outside):
    """The new file tools refuse the link; read_strategy keeps its established behavior."""
    _symlink_or_skip(project / 'strategies' / 'Linked', outside)

    response = api.post('/strategy/get', json={'name': 'Linked'}, headers=HEADERS)

    assert response.status_code == 200
    assert response.json()['content'] == 'class Outside:\n    pass\n'


@pytest.mark.parametrize('root', ['strategies', 'research_scripts'])
def test_symlinked_root_folder_is_refused(project, api, outside, tmp_path, root):
    if root == 'strategies':
        (project / 'strategies').rename(tmp_path / 'real_strategies')
    _symlink_or_skip(project / root, outside)
    before = _snapshot(outside)

    _refused(_post(api, 'list', {'path': root}), 403, 'unsafe_path')
    _refused(_post(api, 'read', {'path': f'{root}/secret.txt'}), 403, 'unsafe_path')
    target = f'{root}/MyStrategy/x.py' if root == 'strategies' else f'{root}/x.py'
    _refused(_post(api, 'write', {'path': target, 'content': 'owned'}), 403, 'unsafe_path')

    assert _snapshot(outside) == before


def test_symlinked_folder_inside_research_scripts_is_not_written_through(project, api, outside):
    (project / 'research_scripts').mkdir()
    _symlink_or_skip(project / 'research_scripts' / 'data', outside)
    before = _snapshot(outside)

    _refused(_post(api, 'write', {'path': 'research_scripts/data/new.py', 'content': 'x'}), 403, 'unsafe_path')
    _refused(_post(api, 'write', {'path': 'research_scripts/data/deeper/new.py', 'content': 'x'}), 403, 'unsafe_path')
    listing = _ok(_post(api, 'list', {'path': 'research_scripts', 'recursive': True}))

    assert [entry['path'] for entry in listing['entries']] == ['research_scripts/data']
    assert _snapshot(outside) == before


def test_symlinked_file_is_never_read_or_written_through(project, api, outside):
    (project / 'research_scripts').mkdir()
    _symlink_or_skip(project / 'research_scripts' / 'link.txt', outside / 'secret.txt')
    before = _snapshot(outside)

    body = _refused(_post(api, 'read', {'path': 'research_scripts/link.txt'}), 403, 'unsafe_path')
    assert 'SECRET' not in body['message']
    _refused(_post(api, 'write', {'path': 'research_scripts/link.txt', 'content': 'owned'}), 409, 'already_exists')
    _refused(_post(api, 'write', {'path': 'research_scripts/link.txt', 'content': 'owned', 'overwrite': True}), 403, 'unsafe_path')
    _refused(_post(api, 'move', {'source': 'research_scripts/link.txt', 'destination': 'research_scripts/moved.txt'}), 403, 'unsafe_path')
    _refused(_post(api, 'copy', {'source': 'research_scripts/link.txt', 'destination': 'research_scripts/copy.txt'}), 403, 'unsafe_path')

    assert (project / 'research_scripts' / 'link.txt').is_symlink()
    assert _snapshot(outside) == before


def test_deleting_symlinks_removes_only_the_links(project, api, outside):
    scripts = project / 'research_scripts'
    (scripts / 'tree').mkdir(parents=True)
    _symlink_or_skip(scripts / 'file_link', outside / 'secret.txt')
    _symlink_or_skip(scripts / 'tree' / 'dir_link', outside)
    before = _snapshot(outside)

    assert _ok(_post(api, 'delete', {'path': 'research_scripts/file_link'}))['type'] == 'symlink'
    deleted = _ok(_post(api, 'delete', {'path': 'research_scripts/tree', 'recursive': True}))

    assert deleted['deleted_files'] == 1 and deleted['deleted_directories'] == 1
    assert list(scripts.iterdir()) == []
    assert _snapshot(outside) == before


def test_copying_a_folder_that_contains_a_symlink_is_refused_without_leftovers(project, api, outside):
    source = project / 'research_scripts' / 'models'
    source.mkdir(parents=True)
    (source / 'model.pkl').write_bytes(MODEL_BYTES)
    _symlink_or_skip(source / 'z_link', outside)

    _refused(_post(api, 'copy', {'source': 'research_scripts/models', 'destination': 'strategies/MyStrategy/models'}), 403, 'unsafe_path')

    assert not (project / 'strategies' / 'MyStrategy' / 'models').exists()
    assert _temp_leftovers(project) == []


def test_write_stays_in_the_opened_folder_when_a_symlink_is_swapped_in_concurrently(project, api, outside, monkeypatch):
    """The parent folder is held open by descriptor, so a swap after resolution cannot redirect the write."""
    scripts = project / 'research_scripts'
    (scripts / 'work').mkdir(parents=True)
    real_temp_name = project_files._temp_name
    swapped = []

    def swap_then_name():
        if not swapped:
            (scripts / 'work').rename(scripts / 'moved_away')
            (scripts / 'work').symlink_to(outside, target_is_directory=True)
            swapped.append(True)
        return real_temp_name()

    monkeypatch.setattr(project_files, '_temp_name', swap_then_name)
    before = _snapshot(outside)

    _ok(_post(api, 'write', {'path': 'research_scripts/work/result.py', 'content': 'safe'}))

    assert swapped
    assert _snapshot(outside) == before
    assert (scripts / 'moved_away' / 'result.py').read_text() == 'safe'


# ---------------------------------------------------------------------------
# Writing, reading, and listing
# ---------------------------------------------------------------------------

def test_write_creates_parents_and_stores_text_exactly(project, api):
    content = '# ✅ script\r\nprint("hi")\n'

    body = _ok(_post(api, 'write', {'path': 'research_scripts/ml/v1/train.py', 'content': content}))

    assert body == {'status': 'success', 'path': 'research_scripts/ml/v1/train.py',
                    'size_bytes': len(content.encode('utf-8')), 'overwritten': False}
    assert (project / 'research_scripts' / 'ml' / 'v1' / 'train.py').read_bytes() == content.encode('utf-8')
    assert _temp_leftovers(project) == []


def test_existing_file_is_replaced_only_with_explicit_overwrite(project, api):
    path = project / 'research_scripts' / 'a.py'
    path.parent.mkdir()
    path.write_text('original', encoding='utf-8')

    body = _refused(_post(api, 'write', {'path': 'research_scripts/a.py', 'content': 'new'}), 409, 'already_exists')
    assert 'overwrite=true' in body['message']
    assert path.read_text() == 'original'

    assert _ok(_post(api, 'write', {'path': 'research_scripts/a.py', 'content': 'new', 'overwrite': True}))['overwritten'] is True
    assert path.read_text() == 'new'
    assert _temp_leftovers(project) == []


def test_write_creates_missing_strategy_folders_but_never_the_strategies_root(project, api, tmp_path):
    _ok(_post(api, 'write', {'path': 'strategies/MyStrategy/helpers/features.py', 'content': 'X = 1\n'}))
    assert (project / 'strategies' / 'MyStrategy' / 'helpers' / 'features.py').read_text() == 'X = 1\n'

    _ok(_post(api, 'write', {'path': 'strategies/NewStrategy/__init__.py', 'content': 'class NewStrategy:\n    pass\n'}))
    assert (project / 'strategies' / 'NewStrategy' / '__init__.py').read_text() == 'class NewStrategy:\n    pass\n'

    (project / 'strategies').rename(tmp_path / 'moved_strategies')
    _refused(_post(api, 'write', {'path': 'strategies/Other/__init__.py', 'content': 'x'}), 404, 'not_found')
    _refused(_post(api, 'mkdir', {'path': 'strategies/Other'}), 404, 'not_found')
    assert not (project / 'strategies').exists()


@pytest.mark.parametrize(('route', 'payload'), [
    ('write', {'path': 'strategies', 'content': 'x'}),
    ('write', {'path': 'research_scripts', 'content': 'x'}),
    ('write', {'path': 'strategies/', 'content': 'x', 'overwrite': True}),
    ('mkdir', {'path': 'strategies'}),
    ('mkdir', {'path': 'research_scripts'}),
    ('delete', {'path': 'strategies', 'recursive': True}),
    ('delete', {'path': 'research_scripts', 'recursive': True}),
    ('delete', {'path': 'strategies/', 'recursive': True}),
    ('move', {'source': 'strategies', 'destination': 'research_scripts/strategies'}),
    ('move', {'source': 'research_scripts', 'destination': 'strategies/Scripts'}),
    ('move', {'source': 'research_scripts/a', 'destination': 'strategies'}),
    ('move', {'source': 'strategies/MyStrategy', 'destination': 'research_scripts', 'overwrite': True}),
    ('copy', {'source': 'research_scripts/a', 'destination': 'strategies'}),
    ('copy', {'source': 'strategies/MyStrategy', 'destination': 'research_scripts', 'overwrite': True}),
])
def test_root_folders_are_protected(project, api, route, payload):
    (project / 'research_scripts' / 'a').mkdir(parents=True)
    before = _snapshot(project)

    _refused(_post(api, route, payload), 403, 'protected_path')

    assert _snapshot(project) == before


def test_write_size_limit_and_folder_targets_are_refused(project, api, monkeypatch):
    monkeypatch.setattr(project_files, 'MAX_WRITE_BYTES', 10)
    (project / 'research_scripts' / 'folder').mkdir(parents=True)

    _refused(_post(api, 'write', {'path': 'research_scripts/big.py', 'content': 'x' * 11}), 413, 'too_large')
    _refused(_post(api, 'write', {'path': 'research_scripts/folder', 'content': 'x'}), 409, 'already_exists')
    _refused(_post(api, 'write', {'path': 'research_scripts/folder', 'content': 'x', 'overwrite': True}), 409, 'wrong_type')
    assert not (project / 'research_scripts' / 'big.py').exists()


def test_text_is_read_in_bounded_pages_with_line_endings_preserved(project, api):
    lines = [f'line {n}\r\n' if n % 2 else f'line {n}\n' for n in range(1, 11)]
    path = project / 'research_scripts' / 'long.txt'
    path.parent.mkdir()
    path.write_bytes(''.join(lines).encode('utf-8'))

    first = _ok(_post(api, 'read', {'path': 'research_scripts/long.txt', 'max_lines': 4}))
    assert first['content'] == ''.join(lines[:4])
    assert (first['start_line'], first['end_line'], first['has_more'], first['next_start_line']) == (1, 4, True, 5)

    last = _ok(_post(api, 'read', {'path': 'research_scripts/long.txt', 'start_line': 9, 'max_lines': 4}))
    assert last['content'] == ''.join(lines[8:])
    assert (last['end_line'], last['has_more']) == (10, False)
    assert 'next_start_line' not in last

    beyond = _ok(_post(api, 'read', {'path': 'research_scripts/long.txt', 'start_line': 50}))
    assert beyond['content'] == '' and beyond['end_line'] is None and beyond['has_more'] is False


def test_read_character_cap_splits_pages_and_cuts_a_single_huge_line(project, api, monkeypatch):
    monkeypatch.setattr(project_files, 'MAX_READ_CHARS', 10)
    path = project / 'research_scripts' / 'wide.txt'
    path.parent.mkdir()
    path.write_text('abcd\nefgh\nijkl\n' + 'x' * 50 + '\nend\n', encoding='utf-8')

    first = _ok(_post(api, 'read', {'path': 'research_scripts/wide.txt'}))
    assert first['content'] == 'abcd\nefgh\n' and first['next_start_line'] == 3

    second = _ok(_post(api, 'read', {'path': 'research_scripts/wide.txt', 'start_line': 3}))
    assert second['content'] == 'ijkl\n' and second['next_start_line'] == 4

    huge = _ok(_post(api, 'read', {'path': 'research_scripts/wide.txt', 'start_line': 4}))
    assert huge['content'] == 'x' * 10
    assert huge['line_truncated'] is True and huge['next_start_line'] == 5

    assert _ok(_post(api, 'read', {'path': 'research_scripts/wide.txt', 'start_line': 5}))['content'] == 'end\n'


@pytest.mark.parametrize('data', [MODEL_BYTES, b'caf\xe9 is latin-1, not UTF-8\n'])
def test_binary_files_return_metadata_but_never_contents(project, api, data):
    path = project / 'research_scripts' / 'model.pkl'
    path.parent.mkdir()
    path.write_bytes(data)

    body = _ok(_post(api, 'read', {'path': 'research_scripts/model.pkl'}))

    assert body['kind'] == 'binary'
    assert body['size_bytes'] == len(data)
    assert 'content' not in body
    assert 'caf' not in body['message'] and 'model\\u0000' not in str(body)


def test_folders_and_special_files_are_not_read(project, api):
    scripts = project / 'research_scripts'
    (scripts / 'folder').mkdir(parents=True)
    _refused(_post(api, 'read', {'path': 'research_scripts/folder'}), 409, 'wrong_type')
    _refused(_post(api, 'read', {'path': 'research_scripts/missing.py'}), 404, 'not_found')

    if not hasattr(os, 'mkfifo'):
        pytest.skip('FIFOs are not available on this platform')
    os.mkfifo(scripts / 'pipe')
    # Would block forever if the FIFO were opened for a blocking read.
    _refused(_post(api, 'read', {'path': 'research_scripts/pipe'}), 409, 'wrong_type')


@pytest.mark.parametrize('payload', [
    {'path': 'research_scripts/a.txt', 'start_line': 0},
    {'path': 'research_scripts/a.txt', 'max_lines': 0},
    {'path': 'research_scripts/a.txt', 'max_lines': project_files.MAX_READ_LINES + 1},
])
def test_read_bounds_are_validated(project, api, payload):
    (project / 'research_scripts').mkdir()
    (project / 'research_scripts' / 'a.txt').write_text('a\n')
    _refused(_post(api, 'read', payload), 400, 'invalid_request')


def test_listing_is_sorted_typed_and_bounded(project, api):
    scripts = project / 'research_scripts'
    (scripts / 'b_dir').mkdir(parents=True)
    (scripts / 'b_dir' / 'inner.py').write_text('x')
    (scripts / 'a.py').write_text('abc')

    flat = _ok(_post(api, 'list', {'path': 'research_scripts'}))
    assert [(e['path'], e['type'], e.get('size_bytes')) for e in flat['entries']] == [
        ('research_scripts/a.py', 'file', 3),
        ('research_scripts/b_dir', 'directory', None),
    ]

    deep = _ok(_post(api, 'list', {'path': 'research_scripts', 'recursive': True}))
    assert [e['path'] for e in deep['entries']] == ['research_scripts/a.py', 'research_scripts/b_dir', 'research_scripts/b_dir/inner.py']
    assert deep['truncated'] is False

    capped = _ok(_post(api, 'list', {'path': 'research_scripts', 'recursive': True, 'max_entries': 2}))
    assert len(capped['entries']) == 2 and capped['truncated'] is True

    _refused(_post(api, 'list', {'path': 'research_scripts', 'max_entries': project_files.MAX_LIST_ENTRIES + 1}), 400, 'invalid_request')
    _refused(_post(api, 'list', {'path': 'research_scripts/a.py'}), 409, 'wrong_type')


def test_mkdir_reports_existing_folders_and_refuses_files(project, api):
    assert _ok(_post(api, 'mkdir', {'path': 'research_scripts/a/b'}))['created'] is True
    assert _ok(_post(api, 'mkdir', {'path': 'research_scripts/a/b'}))['created'] is False
    (project / 'research_scripts' / 'file.py').write_text('x')
    _refused(_post(api, 'mkdir', {'path': 'research_scripts/file.py'}), 409, 'wrong_type')
    _refused(_post(api, 'mkdir', {'path': 'strategies/MyStrategy/__init__.py'}), 409, 'wrong_type')
    assert _ok(_post(api, 'mkdir', {'path': 'strategies/Missing/sub'}))['created'] is True
    assert (project / 'strategies' / 'Missing' / 'sub').is_dir()
    # Reading from a strategy folder that does not exist names the problem precisely.
    _refused(_post(api, 'list', {'path': 'strategies/Absent'}), 404, 'strategy_not_found')
    _refused(_post(api, 'copy', {'source': 'strategies/Absent/model.pkl', 'destination': 'research_scripts/m.pkl'}),
             404, 'strategy_not_found')


# ---------------------------------------------------------------------------
# Moving, copying, deleting
# ---------------------------------------------------------------------------

def test_move_renames_and_refuses_to_clobber_without_overwrite(project, api):
    scripts = project / 'research_scripts'
    scripts.mkdir()
    (scripts / 'a.py').write_text('a')
    (scripts / 'b.py').write_text('b')

    _refused(_post(api, 'move', {'source': 'research_scripts/a.py', 'destination': 'research_scripts/b.py'}), 409, 'already_exists')
    assert (scripts / 'a.py').read_text() == 'a' and (scripts / 'b.py').read_text() == 'b'

    body = _ok(_post(api, 'move', {'source': 'research_scripts/a.py', 'destination': 'research_scripts/b.py', 'overwrite': True}))
    assert body['overwritten'] is True
    assert not (scripts / 'a.py').exists() and (scripts / 'b.py').read_text() == 'a'

    _ok(_post(api, 'move', {'source': 'research_scripts/b.py', 'destination': 'research_scripts/new/dir/c.py'}))
    assert (scripts / 'new' / 'dir' / 'c.py').read_text() == 'a'


def test_move_never_merges_or_nests_folders(project, api):
    scripts = project / 'research_scripts'
    (scripts / 'src' / 'inner').mkdir(parents=True)
    (scripts / 'dst').mkdir()
    (scripts / 'dst' / 'keep.txt').write_text('keep')
    before = _snapshot(project)

    _refused(_post(api, 'move', {'source': 'research_scripts/src', 'destination': 'research_scripts/dst'}), 409, 'already_exists')
    _refused(_post(api, 'move', {'source': 'research_scripts/src', 'destination': 'research_scripts/dst', 'overwrite': True}), 409, 'wrong_type')
    _refused(_post(api, 'move', {'source': 'research_scripts/src', 'destination': 'research_scripts/src/inner/x'}), 400, 'invalid_request')
    assert _snapshot(project) == before

    _ok(_post(api, 'move', {'source': 'research_scripts/src', 'destination': 'strategies/MyStrategy/src'}))
    assert (project / 'strategies' / 'MyStrategy' / 'src' / 'inner').is_dir()


def test_model_artifacts_are_promoted_byte_for_byte_into_a_strategy(project, api):
    models = project / 'research_scripts' / 'ml' / 'models' / 'v1'
    models.mkdir(parents=True)
    (models / 'model.pkl').write_bytes(MODEL_BYTES)
    (models / 'scaler.pkl').write_bytes(MODEL_BYTES[::-1])
    strategy = project / 'strategies' / 'MyStrategy'

    for name in ('model.pkl', 'scaler.pkl'):
        body = _ok(_post(api, 'copy', {'source': f'research_scripts/ml/models/v1/{name}', 'destination': f'strategies/MyStrategy/{name}'}))
        assert body['type'] == 'file' and body['overwritten'] is False
    assert (strategy / 'model.pkl').read_bytes() == MODEL_BYTES
    assert (strategy / 'scaler.pkl').read_bytes() == MODEL_BYTES[::-1]

    # Re-promoting requires an explicit overwrite, and the deployed model stays intact until then.
    (models / 'model.pkl').write_bytes(b'retrained')
    _refused(_post(api, 'copy', {'source': 'research_scripts/ml/models/v1/model.pkl', 'destination': 'strategies/MyStrategy/model.pkl'}), 409, 'already_exists')
    assert (strategy / 'model.pkl').read_bytes() == MODEL_BYTES
    assert _ok(_post(api, 'copy', {'source': 'research_scripts/ml/models/v1/model.pkl', 'destination': 'strategies/MyStrategy/model.pkl', 'overwrite': True}))['overwritten'] is True
    assert (strategy / 'model.pkl').read_bytes() == b'retrained'
    assert (strategy / '__init__.py').read_text() == STRATEGY_CODE
    assert _temp_leftovers(project) == []


def test_folder_copies_are_complete_and_never_merge(project, api):
    source = project / 'research_scripts' / 'rl_model'
    (source / 'nested').mkdir(parents=True)
    (source / 'policy.zip').write_bytes(MODEL_BYTES)
    (source / 'nested' / 'meta.json').write_text('{}')

    body = _ok(_post(api, 'copy', {'source': 'research_scripts/rl_model', 'destination': 'strategies/MyStrategy/rl_model'}))
    assert body['type'] == 'directory' and body['entries'] == 3
    target = project / 'strategies' / 'MyStrategy' / 'rl_model'
    assert (target / 'policy.zip').read_bytes() == MODEL_BYTES and (target / 'nested' / 'meta.json').read_text() == '{}'

    before = _snapshot(project)
    _refused(_post(api, 'copy', {'source': 'research_scripts/rl_model', 'destination': 'strategies/MyStrategy/rl_model'}), 409, 'already_exists')
    _refused(_post(api, 'copy', {'source': 'research_scripts/rl_model', 'destination': 'strategies/MyStrategy/rl_model', 'overwrite': True}), 409, 'already_exists')
    _refused(_post(api, 'copy', {'source': 'research_scripts/rl_model', 'destination': 'research_scripts/rl_model/again'}), 400, 'invalid_request')
    assert _snapshot(project) == before


def test_copy_limits_abort_without_partial_destinations(project, api, monkeypatch):
    source = project / 'research_scripts' / 'big'
    source.mkdir(parents=True)
    (source / 'a.bin').write_bytes(b'x' * 64)
    (source / 'b.bin').write_bytes(b'x' * 64)
    monkeypatch.setattr(project_files, 'MAX_COPY_BYTES', 100)

    _refused(_post(api, 'copy', {'source': 'research_scripts/big', 'destination': 'research_scripts/big_copy'}), 413, 'too_large')
    monkeypatch.setattr(project_files, 'MAX_COPY_BYTES', 10)
    _refused(_post(api, 'copy', {'source': 'research_scripts/big/a.bin', 'destination': 'research_scripts/a_copy.bin'}), 413, 'too_large')

    assert sorted(p.name for p in (project / 'research_scripts').iterdir()) == ['big']
    assert _temp_leftovers(project) == []


def test_delete_needs_recursive_for_non_empty_folders(project, api):
    scripts = project / 'research_scripts'
    (scripts / 'empty').mkdir(parents=True)
    (scripts / 'full' / 'sub').mkdir(parents=True)
    (scripts / 'full' / 'sub' / 'a.py').write_text('a')
    (scripts / 'file.py').write_text('x')

    assert _ok(_post(api, 'delete', {'path': 'research_scripts/file.py'}))['deleted_files'] == 1
    assert _ok(_post(api, 'delete', {'path': 'research_scripts/empty'}))['deleted_directories'] == 1
    _refused(_post(api, 'delete', {'path': 'research_scripts/full'}), 409, 'directory_not_empty')
    assert (scripts / 'full' / 'sub' / 'a.py').exists()

    body = _ok(_post(api, 'delete', {'path': 'research_scripts/full', 'recursive': True}))
    assert (body['deleted_files'], body['deleted_directories']) == (1, 2)
    assert list(scripts.iterdir()) == []
    _refused(_post(api, 'delete', {'path': 'research_scripts/full'}), 404, 'not_found')


def test_strategy_artifacts_can_be_removed_but_the_strategy_folder_is_kept(project, api):
    strategy = project / 'strategies' / 'MyStrategy'
    (strategy / 'model.pkl').write_bytes(MODEL_BYTES)

    _ok(_post(api, 'delete', {'path': 'strategies/MyStrategy/model.pkl'}))

    assert not (strategy / 'model.pkl').exists()
    assert (strategy / '__init__.py').read_text() == STRATEGY_CODE


# ---------------------------------------------------------------------------
# Whole strategy folders
# ---------------------------------------------------------------------------

def _strategy_names(api: TestClient) -> list:
    """The strategy list the dashboard and the strategy tools see."""
    response = api.get('/strategy/all', headers=HEADERS)
    assert response.status_code == 200, response.text
    return sorted(response.json()['strategies'])


def test_strategy_folders_can_be_created_renamed_copied_and_deleted(project, api):
    strategies = project / 'strategies'
    (strategies / 'MyStrategy' / 'model.pkl').write_bytes(MODEL_BYTES)
    (strategies / 'MyStrategy' / 'reports').mkdir()
    (strategies / 'MyStrategy' / 'reports' / 'r.md').write_text('# report\n')

    assert _ok(_post(api, 'mkdir', {'path': 'strategies/Fresh'}))['created'] is True
    assert _strategy_names(api) == ['Fresh', 'MyStrategy']

    renamed = _ok(_post(api, 'move', {'source': 'strategies/MyStrategy', 'destination': 'strategies/Renamed'}))
    assert (renamed['type'], renamed['overwritten']) == ('directory', False)
    assert not (strategies / 'MyStrategy').exists()
    # A generic move never edits code: the class keeps its old name until the assistant changes it.
    assert (strategies / 'Renamed' / '__init__.py').read_text() == STRATEGY_CODE
    assert (strategies / 'Renamed' / 'model.pkl').read_bytes() == MODEL_BYTES
    assert (strategies / 'Renamed' / 'reports' / 'r.md').read_text() == '# report\n'
    assert api.post('/strategy/get', json={'name': 'Renamed'}, headers=HEADERS).json()['content'] == STRATEGY_CODE

    copied = _ok(_post(api, 'copy', {'source': 'strategies/Renamed', 'destination': 'strategies/Variant'}))
    assert (copied['type'], copied['entries'], copied['size_bytes']) == (
        'directory', 4, len(STRATEGY_CODE) + len(MODEL_BYTES) + len('# report\n'))
    assert (strategies / 'Variant' / '__init__.py').read_text() == STRATEGY_CODE
    assert (strategies / 'Variant' / 'model.pkl').read_bytes() == MODEL_BYTES
    assert _strategy_names(api) == ['Fresh', 'Renamed', 'Variant']

    # Out to research_scripts/ and back again.
    _ok(_post(api, 'move', {'source': 'strategies/Variant', 'destination': 'research_scripts/archive/Variant'}))
    _ok(_post(api, 'move', {'source': 'research_scripts/archive/Variant', 'destination': 'strategies/Restored'}))
    assert (strategies / 'Restored' / '__init__.py').read_text() == STRATEGY_CODE

    _refused(_post(api, 'delete', {'path': 'strategies/Restored'}), 409, 'directory_not_empty')
    assert (strategies / 'Restored' / '__init__.py').exists()
    deleted = _ok(_post(api, 'delete', {'path': 'strategies/Restored', 'recursive': True}))
    assert (deleted['type'], deleted['deleted_files'], deleted['deleted_directories']) == ('directory', 3, 2)
    empty = _ok(_post(api, 'delete', {'path': 'strategies/Fresh'}))
    assert (empty['deleted_files'], empty['deleted_directories']) == (0, 1)
    assert _strategy_names(api) == ['Renamed']
    assert _temp_leftovers(project) == []


def test_strategy_folders_are_never_merged_replaced_or_moved_into_themselves(project, api):
    strategies = project / 'strategies'
    (strategies / 'Other').mkdir()
    (strategies / 'Other' / '__init__.py').write_text('class Other:\n    pass\n')
    (strategies / 'Loose.py').write_text('HELPER = 1\n')
    before = _snapshot(project)

    for overwrite in (False, True):
        _refused(_post(api, 'move', {'source': 'strategies/MyStrategy', 'destination': 'strategies/Other', 'overwrite': overwrite}),
                 409, 'already_exists' if not overwrite else 'wrong_type')
        _refused(_post(api, 'copy', {'source': 'strategies/MyStrategy', 'destination': 'strategies/Other', 'overwrite': overwrite}),
                 409, 'already_exists')
        # overwrite replaces a file with a file only, never a folder with a file or a file with a folder.
        _refused(_post(api, 'move', {'source': 'strategies/Loose.py', 'destination': 'strategies/Other', 'overwrite': overwrite}),
                 409, 'already_exists' if not overwrite else 'wrong_type')
        _refused(_post(api, 'move', {'source': 'strategies/Other', 'destination': 'strategies/Loose.py', 'overwrite': overwrite}),
                 409, 'already_exists' if not overwrite else 'wrong_type')
    _refused(_post(api, 'move', {'source': 'strategies/MyStrategy', 'destination': 'strategies/MyStrategy/Nested'}),
             400, 'invalid_request')
    _refused(_post(api, 'copy', {'source': 'strategies/MyStrategy', 'destination': 'strategies/MyStrategy/Nested'}),
             400, 'invalid_request')
    _refused(_post(api, 'move', {'source': 'strategies/MyStrategy', 'destination': 'strategies/MyStrategy'}),
             400, 'invalid_request')
    _refused(_post(api, 'move', {'source': 'strategies/Missing', 'destination': 'strategies/Found'}), 404, 'not_found')
    _refused(_post(api, 'delete', {'path': 'strategies/Missing', 'recursive': True}), 404, 'not_found')

    assert _snapshot(project) == before

    # A loose file directly in strategies/ is an ordinary file, like any other below the roots.
    moved = _ok(_post(api, 'move', {'source': 'strategies/Loose.py', 'destination': 'strategies/Helpers.py'}))
    assert moved['type'] == 'file' and (strategies / 'Helpers.py').read_text() == 'HELPER = 1\n'


@pytest.mark.parametrize(('route', 'payload'), [
    ('mkdir', {'path': 'strategies/../research_scripts/x'}),
    ('mkdir', {'path': 'strategies/./New'}),
    ('move', {'source': 'strategies/MyStrategy', 'destination': 'strategies/../MyStrategy'}),
    ('move', {'source': 'strategies/MyStrategy', 'destination': '/tmp/MyStrategy'}),
    ('move', {'source': 'strategies/MyStrategy', 'destination': '~/MyStrategy'}),
    ('move', {'source': 'strategies/MyStrategy', 'destination': 'strategies\\Renamed'}),
    ('move', {'source': 'strategies/MyStrategy', 'destination': 'storage/MyStrategy'}),
    ('copy', {'source': 'strategies/MyStrategy', 'destination': '../MyStrategy'}),
    ('copy', {'source': 'strategies/MyStrategy', 'destination': 'strategies/Copy/..'}),
    ('delete', {'path': 'strategies/MyStrategy/..', 'recursive': True}),
    ('delete', {'path': 'strategies/..', 'recursive': True}),
])
def test_strategy_folder_operations_refuse_traversal(project, api, route, payload):
    before = _snapshot(project.parent)

    _refused(_post(api, route, payload), 400, 'invalid_path')

    assert _snapshot(project.parent) == before


def test_symlinked_strategy_folders_are_never_moved_copied_or_deleted_through(project, api, outside):
    _symlink_or_skip(project / 'strategies' / 'Linked', outside)
    before_outside = _snapshot(outside)

    _refused(_post(api, 'move', {'source': 'strategies/Linked', 'destination': 'strategies/Moved'}), 403, 'unsafe_path')
    _refused(_post(api, 'copy', {'source': 'strategies/Linked', 'destination': 'strategies/Copied'}), 403, 'unsafe_path')
    _refused(_post(api, 'mkdir', {'path': 'strategies/Linked'}), 403, 'unsafe_path')
    _refused(_post(api, 'move', {'source': 'strategies/MyStrategy', 'destination': 'strategies/Linked'}), 409, 'already_exists')
    _refused(_post(api, 'move', {'source': 'strategies/MyStrategy', 'destination': 'strategies/Linked', 'overwrite': True}),
             409, 'wrong_type')
    assert not (project / 'strategies' / 'Moved').exists() and not (project / 'strategies' / 'Copied').exists()

    deleted = _ok(_post(api, 'delete', {'path': 'strategies/Linked', 'recursive': True}))

    assert (deleted['type'], deleted['deleted_files'], deleted['deleted_directories']) == ('symlink', 1, 0)
    assert not (project / 'strategies' / 'Linked').is_symlink()
    assert _snapshot(outside) == before_outside
    assert (project / 'strategies' / 'MyStrategy' / '__init__.py').read_text() == STRATEGY_CODE


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------

@pytest.fixture
def forward_to_api(api, monkeypatch):
    """Serve the MCP services' HTTP calls with the real routers in-process."""
    calls = []

    def forward_post(url, json=None, headers=None, timeout=None):
        assert url.startswith('http://jesse.test/')
        calls.append({'url': url, 'json': json, 'timeout': timeout})
        return api.post(url.removeprefix('http://jesse.test'), json=json, headers=headers)

    monkeypatch.setattr(project_files_service.mcp_config, 'JESSE_API_URL', 'http://jesse.test')
    monkeypatch.setattr(project_files_service.mcp_config, 'JESSE_PASSWORD', PASSWORD)
    monkeypatch.setattr(project_files_service.requests, 'post', forward_post)
    return calls


@pytest.fixture
def tools(forward_to_api):
    mcp = FakeMCP()
    register_tools(mcp)
    return mcp.tools


def test_mcp_file_tools_work_on_the_jesse_host_through_the_api(project, tools, forward_to_api):
    written = tools['write_project_file']('research_scripts/ml/train.py', 'print(1)\n')
    assert written['status'] == 'success' and written['action'] == 'write_project_file'
    assert 'machine running Jesse' in written['location']

    assert tools['read_project_file']('research_scripts/ml/train.py')['content'] == 'print(1)\n'
    assert [e['path'] for e in tools['list_project_files']('research_scripts', True)['entries']] == [
        'research_scripts/ml', 'research_scripts/ml/train.py']
    assert tools['create_project_directory']('research_scripts/out')['created'] is True
    assert tools['copy_project_path']('research_scripts/ml/train.py', 'research_scripts/out/train.py')['status'] == 'success'
    assert tools['move_project_path']('research_scripts/out/train.py', 'research_scripts/out/renamed.py')['status'] == 'success'
    assert tools['delete_project_path']('research_scripts/out', True)['deleted_files'] == 1

    refused = tools['write_project_file']('research_scripts/ml/train.py', 'again')
    assert (refused['status'], refused['error_type']) == ('error', 'already_exists')
    assert (project / 'research_scripts' / 'ml' / 'train.py').read_text() == 'print(1)\n'

    timeouts = {call['url'].rsplit('/', 1)[-1]: call['timeout'] for call in forward_to_api}
    assert timeouts['copy'] == timeouts['move'] == timeouts['delete'] == project_files_service.TRANSFER_TIMEOUT_SECONDS
    assert timeouts['write'] == project_files_service.REQUEST_TIMEOUT_SECONDS


def test_mcp_file_tools_report_authentication_connection_and_configuration_failures(project, tools, monkeypatch):
    monkeypatch.setattr(project_files_service.mcp_config, 'JESSE_PASSWORD', 'wrong-password')
    assert tools['read_project_file']('research_scripts/a.py')['error_type'] == 'authentication_failed'

    def unreachable(*_args, **_kwargs):
        raise project_files_service.requests.exceptions.ConnectionError('refused')

    monkeypatch.setattr(project_files_service.requests, 'post', unreachable)
    assert tools['list_project_files']()['error_type'] == 'connection_error'

    monkeypatch.setattr(project_files_service.mcp_config, 'JESSE_API_URL', None)
    assert tools['list_project_files']()['error_type'] == 'config_error'


def test_real_mcp_server_registers_the_tools_with_explicit_argument_schemas(project, forward_to_api, monkeypatch):
    server = mcp_server.create_mcp_server(0)
    schemas = {tool.name: tool.inputSchema for tool in asyncio.run(server.list_tools())}

    assert FILE_TOOLS | RESEARCH_TOOLS <= set(schemas)
    assert schemas['write_project_file']['properties']['overwrite']['default'] is False
    assert schemas['delete_project_path']['properties']['recursive']['default'] is False
    assert schemas['copy_project_path']['required'] == ['source', 'destination']
    args = schemas['run_research_script']['properties']['args']
    assert {'type': 'array', 'items': {'type': 'string'}} in args['anyOf']

    # A full round trip through FastMCP's own argument handling and result serialization.
    asyncio.run(server.call_tool('write_project_file', {'path': 'research_scripts/x.py', 'content': 'X = 1\n'}))
    result = asyncio.run(server.call_tool('read_project_file', {'path': 'research_scripts/x.py'}))
    contents = result[0] if isinstance(result, tuple) else result
    assert json.loads(contents[0].text)['content'] == 'X = 1\n'


def test_research_script_policy_is_stated_in_rules_resource_tools_and_server_instructions():
    policy_phrases = [
        'specifically asks for a script',
        'research module',
    ]
    rules = _load_packaged_rules()
    for phrase in policy_phrases:
        assert phrase in rules
    assert 'A generic request to research, find, test, compare, or improve strategies is NOT such a request' in rules
    assert 'never consent to write or run scripts' in rules
    assert 'not sandboxed' in rules
    assert 'jesse://research_scripts' in rules

    mcp = FakeMCP()
    register_resources(mcp)
    guide = mcp.resources['jesse://research_scripts']()
    assert 'A generic request to research, find, test, compare, or improve strategies is NOT such a' in guide
    assert 'not sandboxed' in guide
    assert 'copy_project_path("research_scripts/ml/models/v1/model.pkl", "strategies/MyStrategy/model.pkl")' in guide

    register_tools(mcp)
    run_doc = mcp.tools['run_research_script'].__doc__
    assert 'is NOT such a request and is never consent to write or run scripts' in run_doc
    assert 'NOT sandboxed' in run_doc
    assert 'without a shell' in run_doc
    assert 'is NOT such a' in mcp.tools['write_project_file'].__doc__
    assert 'Research scripts are opt-in' in mcp_server.INSTRUCTIONS


def test_guidance_covers_strategy_folder_lifecycle_and_cancelled_calls():
    def flat(text: str) -> str:
        return ' '.join(text.split())

    rules = flat(_load_packaged_rules())
    mcp = FakeMCP()
    register_resources(mcp)
    guide = flat(mcp.resources['jesse://research_scripts']())
    analysis_guide = flat(mcp.resources['jesse://session_analysis']())
    register_tools(mcp)
    docs = {name: flat(mcp.tools[name].__doc__) for name in FILE_TOOLS}

    for text in (rules, guide):
        assert 'rename its Strategy class to the new folder name' in text or \
            'rename the Strategy class in its `__init__.py` to the new folder name' in text
        assert 'whole strategy folders (`strategies/<Name>`)' in text
    assert 'may still have finished on the Jesse host' in rules
    assert 'may still finish on the Jesse host' in guide and 'get_research_job_status()' in guide
    assert 'get_analysis_job()' in analysis_guide and 'cancel_analysis_job' in analysis_guide
    assert 'rename the Strategy class in its __init__.py to the new folder name' in docs['move_project_path']
    assert 'change the copied Strategy class name' in docs['copy_project_path']
    assert 'whole strategy folder' in docs['delete_project_path']
    for text in [rules, guide, *docs.values()]:
        for stale in ('top-level strategy folder', 'strategy folders themselves', 'inside an existing strategy folder',
                      'cannot be created, moved, or deleted'):
            assert stale not in text


def test_no_tool_offers_uploads_downloads_or_other_roots():
    """The file tools reach only the two roots; there is no transfer tool for arbitrary files."""
    assert project_files.ROOTS == ('strategies', 'research_scripts')
    mcp = FakeMCP()
    register_tools(mcp)
    assert not any('upload' in name or 'download' in name for name in mcp.tools)
    for name in FILE_TOOLS:
        assert 'research_scripts' in mcp.tools[name].__doc__, name


# ---------------------------------------------------------------------------
# Filesystems without hard links
# ---------------------------------------------------------------------------

@pytest.fixture
def no_hard_links(monkeypatch):
    """Behave like a network/FUSE volume where link() is not permitted."""
    def refuse_link(*_args, **_kwargs):
        raise OSError(errno.EPERM, 'Operation not permitted')

    monkeypatch.setattr(project_files.os, 'link', refuse_link)
    # The platform probe checks os.link's capabilities; the platform itself is still supported.
    monkeypatch.setattr(project_files, '_platform_supported', lambda: True)


def test_without_hard_links_publishing_still_never_clobbers(project, api, no_hard_links):
    _ok(_post(api, 'write', {'path': 'research_scripts/a.py', 'content': 'A = 1\n'}))
    assert (project / 'research_scripts' / 'a.py').read_text() == 'A = 1\n'

    _refused(_post(api, 'write', {'path': 'research_scripts/a.py', 'content': 'B'}), 409, 'already_exists')
    _refused(_post(api, 'copy', {'source': 'strategies/MyStrategy/__init__.py', 'destination': 'research_scripts/a.py'}),
             409, 'already_exists')
    assert (project / 'research_scripts' / 'a.py').read_text() == 'A = 1\n'

    _ok(_post(api, 'write', {'path': 'research_scripts/b.py', 'content': 'B = 2\n'}))
    _refused(_post(api, 'move', {'source': 'research_scripts/b.py', 'destination': 'research_scripts/a.py'}), 409, 'already_exists')
    moved = _ok(_post(api, 'move', {'source': 'research_scripts/b.py', 'destination': 'research_scripts/c.py'}))
    assert moved['overwritten'] is False and (project / 'research_scripts' / 'c.py').read_text() == 'B = 2\n'
    assert not (project / 'research_scripts' / 'b.py').exists() and _temp_leftovers(project) == []


def test_a_failed_rename_into_a_reserved_name_leaves_no_placeholder(project, api, no_hard_links, monkeypatch):
    real_rename = os.rename

    def failing_rename(src, dst, *args, **kwargs):
        if dst == 'new.py':
            raise OSError(errno.EIO, 'I/O error')
        return real_rename(src, dst, *args, **kwargs)

    monkeypatch.setattr(project_files.os, 'rename', failing_rename)
    _refused(_post(api, 'write', {'path': 'research_scripts/new.py', 'content': 'X'}), 500, 'io_error')
    assert not (project / 'research_scripts' / 'new.py').exists() and _temp_leftovers(project) == []


def test_a_placeholder_replaced_by_another_process_is_not_removed(project, no_hard_links, monkeypatch):
    """If someone else replaced our reserved name before the rename failed, their file stays."""
    folder = project / 'research_scripts'
    folder.mkdir()
    (folder / 'src.tmp').write_text('ours')
    real_rename = os.rename

    def replace_then_fail(src, dst, *args, **kwargs):
        (folder / 'theirs').write_text('theirs')
        real_rename(folder / 'theirs', folder / 'dst.py')
        raise OSError(errno.EIO, 'I/O error')

    monkeypatch.setattr(project_files.os, 'rename', replace_then_fail)
    fd = os.open(folder, os.O_RDONLY)
    try:
        with pytest.raises(OSError):
            project_files._rename_into_reserved_name(fd, 'src.tmp', fd, 'dst.py', 'research_scripts/dst.py')
    finally:
        os.close(fd)
    assert (folder / 'dst.py').read_text() == 'theirs'
