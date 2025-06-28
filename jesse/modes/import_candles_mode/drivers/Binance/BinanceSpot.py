from .BinanceMain import BinanceMain
from jesse.enums import Exchanges


class BinanceSpot(BinanceMain):
    def __init__(self) -> None:
        super().__init__(
            name=Exchanges.BINANCE_SPOT.value,
            rest_endpoint='https://api.binance.com/api',
            backup_exchange_class=None
        )
