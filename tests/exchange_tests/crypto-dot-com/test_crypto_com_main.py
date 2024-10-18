import pytest

from unittest.mock import patch, MagicMock
from jesse.modes.import_candles_mode.drivers.CryptoCom.CryptoComMain import CryptoComMain

class TestCryptoComMain:
    @pytest.fixture
    def crypto_com_main(self):
        class CryptoComMainTest(CryptoComMain):
            def _get_mapped_symbol_name(self, dashy_symbol):
                return dashy_symbol.replace('-', '_')

        return CryptoComMainTest(name="crypto_com", backup_exchange_class=None)

    @patch('requests.get')
    def test_get_starting_time(self, mock_get, crypto_com_main):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'result': {
                'data': [{'t': 1609459200000}]  # 2021-01-01 00:00:00 UTC
            }
        }
        mock_get.return_value = mock_response

        result = crypto_com_main.get_starting_time('BTC-USDT')

        assert result == 1609545600000  # 2021-01-02 00:00:00 UTC
        mock_get.assert_called_once_with(
            'https://api.crypto.com/exchange/v1/public/get-candlestick',
            params={
                'timeframe': '1d',
                'instrument_name': 'BTC_USDT',
                'count': 1500,
            }
        )

    @patch('requests.get')
    def test_fetch(self, mock_get, crypto_com_main):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'result': {
                'data': [
                    {'t': 1609459200000, 'o': '29000', 'c': '29100', 'h': '29200', 'l': '28900', 'v': '100'},
                    {'t': 1609459260000, 'o': '29100', 'c': '29150', 'h': '29200', 'l': '29050', 'v': '50'},
                ]
            }
        }
        mock_get.return_value = mock_response

        result = crypto_com_main.fetch('BTC-USDT', 1609459200000, '1m')

        assert len(result) == 2
        assert result[0]['timestamp'] == 1609459200000
        assert result[0]['open'] == 29000.0
        assert result[1]['close'] == 29150.0
        mock_get.assert_called_once()

    @patch('requests.get')
    def test_get_available_symbols(self, mock_get, crypto_com_main):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'result': {
                'data': [
                    {'base_ccy': 'BTC', 'quote_ccy': 'USDT', 'inst_type': 'CCY_PAIR'},
                    {'base_ccy': 'ETH', 'quote_ccy': 'USDT', 'inst_type': 'PERPETUAL_SWAP'},
                ]
            }
        }
        mock_get.return_value = mock_response

        result = crypto_com_main.get_available_symbols()

        assert result == ['BTC-USDT', 'ETH-USDT']
        mock_get.assert_called_once_with('https://api.crypto.com/exchange/v1/public/get-instruments')

    def test_filter_by_inst_type(self, crypto_com_main):
        item_spot = {'inst_type': 'SPOT'}
        item_future = {'inst_type': 'FUTURE'}

        assert crypto_com_main._filter_by_inst_type(item_spot) == True
        assert crypto_com_main._filter_by_inst_type(item_future) == True

        crypto_com_main.instrument_type = 'SPOT'
        assert crypto_com_main._filter_by_inst_type(item_spot) == True
        assert crypto_com_main._filter_by_inst_type(item_future) == False

    def test_dashy_symbol(self, crypto_com_main):
        assert crypto_com_main._dashy_symbol('BTC', 'USDT') == 'BTC-USDT'

    def test_prefix_address(self, crypto_com_main):
        assert crypto_com_main._prefix_address == '/exchange/v1/public/'