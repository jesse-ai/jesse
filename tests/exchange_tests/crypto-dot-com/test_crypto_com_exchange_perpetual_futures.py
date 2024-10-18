import pytest

from jesse.enums import exchanges
from jesse.modes.import_candles_mode.drivers.CryptoCom.CryptoComExchangePerpetualFutures import CryptoComExchangePerpetualFutures

class TestCryptoComExchangePerpetualFutures:

    @pytest.fixture
    def crypto_com_exchange_perpetual_futures(self):
        class CryptoComExchangePerpetualFuturesTest(CryptoComExchangePerpetualFutures):
            def __init__(self) -> None:
                    super().__init__()

        return CryptoComExchangePerpetualFuturesTest()

    def test_init_params(self, crypto_com_exchange_perpetual_futures):
        assert crypto_com_exchange_perpetual_futures.name == exchanges.CRYPTO_COM_EXCHANGE_PERPETUAL_FUTURES
        assert crypto_com_exchange_perpetual_futures.instrument_type == 'PERPETUAL_SWAP'
        assert crypto_com_exchange_perpetual_futures._backup_exchange_class == None

    def test__get_mapped_symbol_name(self, crypto_com_exchange_perpetual_futures):
        assert crypto_com_exchange_perpetual_futures._get_mapped_symbol_name('BTC-USD') == 'BTCUSD-PERP'
