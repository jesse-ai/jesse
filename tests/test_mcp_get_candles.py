from unittest import mock

from jesse.mcp.tools.services import candles


class _Response:
    status_code = 200

    def __init__(self, data):
        self._data = data

    def json(self):
        return {'data': self._data}


def _get(data, **kwargs):
    with mock.patch.object(candles.requests, 'post', return_value=_Response(data)), \
            mock.patch.object(candles, 'hash_password', return_value='hashed'):
        return candles.get_candles_service('Binance Perpetual Futures', 'BTC-USDT', '4h', **kwargs)


def test_an_empty_window_explains_why_instead_of_looking_like_an_empty_database():
    result = _get([])

    assert result['status'] == 'success'
    assert result['candle_count'] == 0
    assert 'does not mean nothing is stored' in result['message']
    assert 'generate_candles_from_1m' in result['message']


def test_a_window_returns_its_newest_candles():
    result = _get([{'time': t} for t in (1, 2, 3)], limit=2)

    assert result['candles'] == [{'time': 2}, {'time': 3}]
    assert result['truncated'] is True
    assert result['message'].startswith('Returned the newest 2 of 3 4h candles')
