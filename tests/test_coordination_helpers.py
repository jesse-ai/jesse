"""Check actual Jesse helper failure policy in the isolated Python environment.

Run from the core checkout, which is not a trading project. Stub only
network operations and logging; import the real helper and serializer code.
"""
import json
import base64
import gzip
import unittest
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

from jesse.services import redis as helpers
from jesse.services.coordination_client import (
    CoordinationCapacityError, CoordinationConnectionError, CoordinationError, CoordinationSizeError,
)


class HelperFailurePolicy(unittest.TestCase):
    def setUp(self):
        self.patches = [patch.object(helpers.jh, 'is_unit_testing', return_value=False),
                        patch.object(helpers.jh, 'app_mode', return_value='backtest'),
                        patch.object(helpers.jh, 'terminal_debug'),
                        patch.dict(helpers.ENV_VALUES, {'APP_PORT': '19081'}),
                        patch.object(helpers, 'RedisConnectionError', CoordinationConnectionError),
                        patch.object(helpers, '_last_active_check_error_at', 0),
                        patch.object(helpers, 'sync_redis')]
        self.mocks = [p.start() for p in self.patches]
        for item in self.patches:
            self.addCleanup(item.stop)
        self.client = self.mocks[-1]

    def test_publish_connection_failure_is_logged(self):
        self.client.publish.side_effect = CoordinationConnectionError('busy: slots full')
        helpers.sync_publish('progress', {'value': 1})
        self.mocks[2].assert_called_once()

    def test_capacity_and_size_failure_are_visible(self):
        for error in [CoordinationCapacityError('capacity: event too large'),
                      CoordinationSizeError('body too large')]:
            self.client.publish.side_effect = error
            with self.assertRaises(type(error)):
                helpers.sync_publish('results', {'value': 1})

    def test_serialization_error_retains_logged_failure_policy(self):
        helpers.sync_publish('results', object())
        self.client.publish.assert_not_called()
        self.mocks[2].assert_called_once()

    def test_active_check_preserves_fail_open_policy(self):
        # This is the existing worker policy, not a claim of safe live failover.
        for message in ['busy: slots full', 'restart: generation changed']:
            self.client.sismember.side_effect = CoordinationConnectionError(message)
            self.assertTrue(helpers.is_process_active('synthetic-session'))

    def test_managed_active_check_confirms_the_service_before_cancelling(self):
        # Fake only RPC outcomes; no credentials, ports or live service are used.
        self.client.address = ('127.0.0.1', 0)
        self.client.token = 'synthetic-not-a-credential'
        self.client.namespace = 'synthetic'
        self.client.generation = 'first-generation'
        self.client.sismember.side_effect = CoordinationConnectionError('retired connection')
        with patch.dict(os.environ, {'JESSE_COORDINATION_RUNTIME': 'synthetic'}), patch.object(helpers, 'Client') as factory:
            factory.return_value.connect.return_value = 'first-generation'
            self.assertTrue(helpers.is_process_active('synthetic-session'))
            factory.return_value.connect.return_value = 'different-generation'
            self.assertFalse(helpers.is_process_active('synthetic-session'))
            factory.return_value.connect.side_effect = CoordinationError('auth: invalid credentials')
            self.assertFalse(helpers.is_process_active('synthetic-session'))

    def test_managed_active_check_stops_on_a_reassigned_authenticated_port(self):
        self.client.sismember.side_effect = CoordinationError('auth: invalid credentials')
        with patch.dict(os.environ, {'JESSE_COORDINATION_RUNTIME': 'synthetic'}):
            self.assertFalse(helpers.is_process_active('synthetic-session'))

    def test_compressed_helper_envelope_preserves_payload(self):
        helpers.sync_publish('results', {'series': list(range(200000))}, compression=True)
        self.client.publish.assert_called_once()
        self.assertEqual(self.client.publish.call_args.args[0], '19081:channel:1')
        envelope = json.loads(self.client.publish.call_args.args[1])
        self.assertTrue(envelope['is_compressed'])
        restored = json.loads(gzip.decompress(base64.b64decode(envelope['data'])))
        self.assertEqual(restored, {'series': list(range(200000))})


if __name__ == '__main__':
    unittest.main(verbosity=2)


@pytest.mark.parametrize('redis_unavailable', [False, True], ids=['existing-environment', 'without-redis'])
def test_native_backend_and_optuna_work_without_redis(tmp_path, redis_unavailable):
    """Rust helpers and SQLite studies work even when Redis clients cannot be imported."""
    env = os.environ.copy()
    env.pop('COORDINATION_BACKEND', None)
    # Optuna optionally imports installed Redis clients while loading its storage
    # backends. Simulate missing packages instead of forbidding that optional import;
    # this also exercises environments where compatibility clients remain installed.
    script = '''
import importlib.abc
from pathlib import Path
import sys

redis_unavailable = sys.argv[1] == 'True'
if redis_unavailable:
    class MissingRedis(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split('.')[0] in {'redis', 'aioredis'}:
                raise ModuleNotFoundError(fullname, name=fullname)

    sys.meta_path.insert(0, MissingRedis())

from jesse.services.redis import BACKEND
assert BACKEND == 'rust'
import optuna

optuna.logging.set_verbosity(optuna.logging.ERROR)
storage = 'sqlite:///' + Path(sys.argv[2]).as_posix()
study = optuna.create_study(storage=storage, study_name='without-redis')
study.optimize(lambda trial: trial.suggest_float('x', 0, 1), n_trials=1)
loaded = optuna.load_study(storage=storage, study_name='without-redis')
assert len(loaded.trials) == 1
assert loaded.trials[0].state == optuna.trial.TrialState.COMPLETE
assert loaded.best_value == study.best_value
if redis_unavailable:
    assert 'redis' not in sys.modules and 'aioredis' not in sys.modules
'''
    # Full core imports are slower in the Windows VM; bound a stalled child at 30 seconds.
    result = subprocess.run(
        [sys.executable, '-c', script, str(redis_unavailable), str(tmp_path / 'study.db')],
        cwd=Path(__file__).resolve().parents[1], env=env,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('backend, accepted', [('redis', True), ('unknown', False)])
def test_removed_backend_setting_handles_migration(backend, accepted):
    """Old Redis projects upgrade automatically; misspelled backend settings still fail."""
    result = subprocess.run(
        [sys.executable, '-c', 'from jesse.services.redis import BACKEND; assert BACKEND == "rust"'],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'COORDINATION_BACKEND': backend},
        capture_output=True, text=True, timeout=30,
    )
    if accepted:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0
        assert 'Only the Rust coordinator is supported' in result.stderr
