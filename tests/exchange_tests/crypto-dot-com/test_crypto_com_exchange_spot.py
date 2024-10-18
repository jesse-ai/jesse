import pytest

from jesse.enums import exchanges
from jesse.modes.import_candles_mode.drivers.CryptoCom.CryptoComExchangeSpot import CryptoComExchangeSpot

class TestCryptoComExchangeSpot:

    @pytest.fixture
    def crypto_com_exchange_spot(self):
        class CryptoComExchangeSpotTest(CryptoComExchangeSpot):
            def __init__(self) -> None:
                    super().__init__()

        return CryptoComExchangeSpotTest()

    def test_init_params(self, crypto_com_exchange_spot):
        assert crypto_com_exchange_spot.name == exchanges.CRYPTO_COM_EXCHANGE_SPOT
        assert crypto_com_exchange_spot.instrument_type == 'CCY_PAIR'
        assert crypto_com_exchange_spot._backup_exchange_class == None

    def test__get_mapped_symbol_name(self, crypto_com_exchange_spot):
        assert crypto_com_exchange_spot._get_mapped_symbol_name('BTC-USD') == 'BTC_USD'
