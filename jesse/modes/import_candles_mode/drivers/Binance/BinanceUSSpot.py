from .BinanceMain import BinanceMain
from jesse.enums import Exchanges


class BinanceUSSpot(BinanceMain):
    def __init__(self) -> None:
        from .BinanceSpot import BinanceSpot

        super().__init__(
            name=Exchanges.BINANCE_US_SPOT.value,
            rest_endpoint='https://api.binance.us/api',
            backup_exchange_class=BinanceSpot
        )
