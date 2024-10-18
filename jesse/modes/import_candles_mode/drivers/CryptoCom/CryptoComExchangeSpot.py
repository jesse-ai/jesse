from .CryptoComMain import CryptoComMain
from jesse.enums import exchanges
import jesse.helpers as jh


class CryptoComExchangeSpot(CryptoComMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.CRYPTO_COM_EXCHANGE_SPOT,
            backup_exchange_class=None,
            instrument_type='CCY_PAIR'
        )

    def _get_mapped_symbol_name(self, dashy_symbol):
        return jh.dashy_to_underline(dashy_symbol)