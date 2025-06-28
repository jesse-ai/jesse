from .BinanceMain import BinanceMain
from jesse.enums import Exchanges


class BinancePerpetualFutures(BinanceMain):
    def __init__(self) -> None:
        from .BinanceSpot import BinanceSpot

        super().__init__(
            name=Exchanges.BINANCE_PERPETUAL_FUTURES.value,
            rest_endpoint='https://fapi.binance.com/fapi',
            backup_exchange_class=BinanceSpot
        )
