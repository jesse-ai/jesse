from .CryptoComMain import CryptoComMain
from jesse.enums import exchanges
import jesse.helpers as jh


class CryptoComExchangePerpetualFutures(CryptoComMain):
    def __init__(self) -> None:
        from .CryptoComExchangeSpot import CryptoComExchangeSpot

        super().__init__(
            name=exchanges.CRYPTO_COM_EXCHANGE_PERPETUAL_FUTURES,
            backup_exchange_class=None,
            instrument_type = 'PERPETUAL_SWAP'
        )

    def _get_mapped_symbol_name(self, dashy_symbol):
        return f"{jh.dashless_symbol(dashy_symbol)}-PERP"


