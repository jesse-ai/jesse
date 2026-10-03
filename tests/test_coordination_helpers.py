"""Check actual Jesse helper failure policy in the isolated Python environment.

Run from the core checkout, which is not a trading project. Stub only
network operations and logging; import the real helper and serializer code.
"""
import json
import base64
import gzip
import unittest
from unittest.mock import patch

from jesse.services import redis as helpers
from jesse.services.coordination_client import (
    CoordinationCapacityError, CoordinationConnectionError, CoordinationSizeError,
)


class HelperFailurePolicy(unittest.TestCase):
    def setUp(self):
        self.patches = [patch.object(helpers.jh, 'is_unit_testing', return_value=False),
                        patch.object(helpers.jh, 'app_mode', return_value='backtest'),
                        patch.object(helpers.jh, 'terminal_debug'),
                        patch.dict(helpers.ENV_VALUES, {'APP_PORT': '19081'}),
                        patch.object(helpers, 'BACKEND', 'rust'),
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
