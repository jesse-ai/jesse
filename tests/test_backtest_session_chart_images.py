import importlib
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jesse.controllers import backtest_controller
from jesse.services import auth, transformers

# jesse.models re-exports the model class under the module's name, so load the
# module itself to reach its DB helper functions.
backtest_session_model = importlib.import_module('jesse.models.BacktestSession')


PASSWORD = 'chart-images-password'
AUTHORIZATION = sha256(PASSWORD.encode('utf-8')).hexdigest()


@pytest.fixture
def charts_folder(tmp_path, monkeypatch):
    """Resolve the relative storage/backtest-charts path inside a disposable project."""
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / 'storage' / 'backtest-charts'
    folder.mkdir(parents=True)
    return folder


@pytest.fixture
def db_updates(monkeypatch):
    """Treat the session as persisted and record the reset instead of touching a database."""
    updates = []

    class _Query:
        def __init__(self, values: dict):
            self.values = values

        def where(self, *args):
            return self

        def execute(self):
            updates.append(self.values)
            return 1

    monkeypatch.setattr(
        backtest_session_model,
        'get_backtest_session_by_id',
        lambda session_id: SimpleNamespace(id=session_id),
    )
    monkeypatch.setattr(
        backtest_session_model.BacktestSession,
        'update',
        lambda **values: _Query(values),
    )
    return updates


@pytest.fixture
def api_client(monkeypatch) -> TestClient:
    monkeypatch.setitem(auth.ENV_VALUES, 'PASSWORD', PASSWORD)
    app = FastAPI()

    @app.exception_handler(auth.InvalidAuthError)
    async def invalid_auth_handler(_request, _exc):
        return auth.unauthorized_response()

    app.include_router(backtest_controller.router)
    return TestClient(app)


def _write_charts(folder, session_id: str, content: bytes) -> None:
    for chart_name in backtest_controller.BACKTEST_CHART_NAMES:
        (folder / f'{session_id}_{chart_name}.png').write_bytes(content)


def _chart_response(client: TestClient, session_id: str, chart_name: str):
    # The dashboard's cache-busting `t` is ignored by the server; a fixed value
    # proves the file on disk, not the URL, decides which run is served.
    return client.get(
        f'/backtest/sessions/{session_id}/charts-image',
        params={'chart': chart_name, 't': 1},
        headers={'Authorization': AUTHORIZATION},
    )


def test_same_id_rerun_removes_only_that_sessions_previous_chart_images(charts_folder, db_updates):
    # regression: a same-ID rerun reset the stored results but kept the previous
    # run's chart PNGs, which were then still reported and served as available.
    session_id = str(uuid4())
    other_session_id = str(uuid4())
    _write_charts(charts_folder, session_id, b'previous-run')
    _write_charts(charts_folder, other_session_id, b'other-session')

    backtest_session_model.store_backtest_session(id=session_id, status='running')

    assert not list(charts_folder.glob(f'{session_id}_*.png'))
    assert len(list(charts_folder.glob(f'{other_session_id}_*.png'))) == len(
        backtest_controller.BACKTEST_CHART_NAMES
    )
    assert len(db_updates) == 1
    assert db_updates[0]['status'] == 'running'
    assert db_updates[0]['metrics'] is None


def test_new_session_does_not_touch_existing_chart_images(charts_folder, monkeypatch):
    session_id = str(uuid4())
    other_session_id = str(uuid4())
    _write_charts(charts_folder, other_session_id, b'other-session')
    inserted = []

    class _Insert:
        def __init__(self, values: dict):
            self.values = values

        def execute(self):
            inserted.append(self.values)

    monkeypatch.setattr(backtest_session_model, 'get_backtest_session_by_id', lambda session_id: None)
    monkeypatch.setattr(
        backtest_session_model.BacktestSession,
        'insert',
        lambda **values: _Insert(values),
    )

    backtest_session_model.store_backtest_session(id=session_id, status='running')

    assert [row['id'] for row in inserted] == [session_id]
    assert len(list(charts_folder.glob(f'{other_session_id}_*.png'))) == len(
        backtest_controller.BACKTEST_CHART_NAMES
    )


def test_same_id_rerun_serves_only_the_new_runs_chart_images(charts_folder, db_updates, api_client):
    # regression: after rerunning a session with the same ID, the equity chart
    # endpoint and has_charts_image probe must never expose the previous run.
    session_id = str(uuid4())
    _write_charts(charts_folder, session_id, b'previous-run')

    first = _chart_response(api_client, session_id, 'equity_curve')
    assert first.status_code == 200
    assert first.content == b'previous-run'

    backtest_session_model.store_backtest_session(id=session_id, status='running')

    for chart_name in backtest_controller.BACKTEST_CHART_NAMES:
        assert _chart_response(api_client, session_id, chart_name).status_code == 404
    session = SimpleNamespace(
        id=session_id,
        status='running',
        metrics=None,
        equity_curve=None,
        trades=None,
        hyperparameters=None,
        chart_data=None,
        created_at=1,
        updated_at=2,
        execution_duration=None,
        state_json={},
        exception=None,
        traceback=None,
        title=None,
        description=None,
        strategy_codes_json={},
    )
    assert transformers.get_backtest_session_for_load_more(session)['has_charts_image'] is False

    _write_charts(charts_folder, session_id, b'new-run')

    for chart_name in backtest_controller.BACKTEST_CHART_NAMES:
        response = _chart_response(api_client, session_id, chart_name)
        assert response.status_code == 200
        assert response.content == b'new-run'
    assert transformers.get_backtest_session_for_load_more(session)['has_charts_image'] is True
