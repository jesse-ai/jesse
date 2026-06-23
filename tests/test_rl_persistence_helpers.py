"""
Unit tests for the RL bundle persistence helpers — the pure functions behind
TrainResult.save / load_rl_agent. These touch no global backtest state and run
no training, so they are tested directly (fast), unlike the end-to-end RL tests
that use a subprocess.

Covers the branches the end-to-end save/load test does not exercise: the
string-strategy-name path (vs a class), the graceful "source can't be captured"
fallback, and the default-directory resolution.
"""
import os

import pytest

# Skip the whole module unless the RL extras are installed.
pytest.importorskip("stable_baselines3")
pytest.importorskip("gymnasium")

from jesse.research.reinforcement_learning import (  # noqa: E402
    _sha256, _current_versions, _serialize_routes, _reconstruct_routes,
    _capture_strategy_source, _default_models_dir, ALGORITHMS,
)

EXCH, SYM = 'Binance Perpetual Futures', 'BTC-USDT'


def test_supported_algorithms_registry():
    from stable_baselines3 import DQN, PPO
    assert ALGORITHMS == {'DQN': DQN, 'PPO': PPO}


def _rl_strategy_class():
    import importlib
    return getattr(importlib.import_module('jesse.strategies.RLEasyMomentum'), 'RLEasyMomentum')


# --------------------------------------------------------------------------- #
# _sha256 / _current_versions
# --------------------------------------------------------------------------- #
def test_sha256_is_deterministic_and_none_safe():
    assert _sha256("abc") == _sha256("abc")
    assert _sha256("abc") != _sha256("abd")
    assert _sha256(None) is None


def test_current_versions_reports_three_libraries():
    v = _current_versions()
    assert set(v) == {"jesse", "stable_baselines3", "python"}
    # SB3 and Python must always resolve; jesse should too in a normal checkout.
    assert v["stable_baselines3"] and v["python"]


# --------------------------------------------------------------------------- #
# _serialize_routes <-> _reconstruct_routes
# --------------------------------------------------------------------------- #
def test_routes_roundtrip_for_class_strategy():
    cls = _rl_strategy_class()
    routes = [{'exchange': EXCH, 'strategy': cls, 'symbol': SYM, 'timeframe': '1m'}]

    serialized = _serialize_routes(routes)
    assert serialized[0]['strategy'] == f"{cls.__module__}.{cls.__qualname__}"
    assert serialized[0]['strategy_kind'] == 'class_path'

    rebuilt = _reconstruct_routes(serialized)
    assert rebuilt[0]['strategy'] is cls            # re-imported to the same class object
    assert 'strategy_kind' not in rebuilt[0]        # internal marker stripped


def test_routes_roundtrip_for_string_name_strategy():
    routes = [{'exchange': EXCH, 'strategy': 'MyRLStrategy', 'symbol': SYM, 'timeframe': '1m'}]

    serialized = _serialize_routes(routes)
    assert serialized[0]['strategy'] == 'MyRLStrategy'
    assert serialized[0]['strategy_kind'] == 'name'

    rebuilt = _reconstruct_routes(serialized)
    assert rebuilt[0]['strategy'] == 'MyRLStrategy'  # names pass through verbatim
    assert 'strategy_kind' not in rebuilt[0]


def test_reconstruct_routes_raises_on_missing_class():
    serialized = [{'exchange': EXCH, 'symbol': SYM, 'timeframe': '1m',
                   'strategy': 'no.such.module.Ghost', 'strategy_kind': 'class_path'}]
    with pytest.raises(ImportError):
        _reconstruct_routes(serialized)


# --------------------------------------------------------------------------- #
# _capture_strategy_source
# --------------------------------------------------------------------------- #
def test_capture_source_from_class_reads_whole_module_file():
    cls = _rl_strategy_class()
    source, identity, kind = _capture_strategy_source(cls)
    assert kind == 'class_path'
    assert identity.endswith('RLEasyMomentum')
    # whole-file capture: includes the class plus its module-level imports
    assert 'class RLEasyMomentum' in source
    assert 'import' in source


def test_capture_source_falls_back_gracefully_when_unavailable():
    # A builtin class has no capturable source file; capture must degrade to
    # (None, identity, kind) rather than raising.
    source, identity, kind = _capture_strategy_source(dict)
    assert source is None
    assert kind == 'class_path'
    assert identity.endswith('dict')


def test_capture_source_from_string_name_reads_strategies_dir(tmp_path, monkeypatch):
    strat_dir = tmp_path / "strategies" / "Foo"
    strat_dir.mkdir(parents=True)
    (strat_dir / "__init__.py").write_text("# Foo strategy source\nclass Foo: pass\n")
    monkeypatch.chdir(tmp_path)

    source, identity, kind = _capture_strategy_source("Foo")
    assert kind == 'name'
    assert identity == 'Foo'
    assert 'Foo strategy source' in source


def test_capture_source_string_name_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source, identity, kind = _capture_strategy_source("DoesNotExist")
    assert source is None and identity == 'DoesNotExist' and kind == 'name'


# --------------------------------------------------------------------------- #
# _default_models_dir
# --------------------------------------------------------------------------- #
def test_default_models_dir_for_class_is_next_to_strategy_file():
    import sys
    cls = _rl_strategy_class()
    routes = [{'exchange': EXCH, 'strategy': cls, 'symbol': SYM, 'timeframe': '1m'}]
    strat_file_dir = os.path.dirname(os.path.abspath(sys.modules[cls.__module__].__file__))

    d = _default_models_dir(routes)
    assert d == os.path.join(strat_file_dir, 'rl_models')


def test_default_models_dir_for_existing_named_strategy(tmp_path, monkeypatch):
    (tmp_path / "strategies" / "Foo").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    routes = [{'exchange': EXCH, 'strategy': 'Foo', 'symbol': SYM, 'timeframe': '1m'}]
    assert _default_models_dir(routes) == os.path.join('strategies/Foo', 'rl_models')


def test_default_models_dir_falls_back_to_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    routes = [{'exchange': EXCH, 'strategy': 'Unknown', 'symbol': SYM, 'timeframe': '1m'}]
    assert _default_models_dir(routes) == os.path.join(str(tmp_path), 'rl_models')
