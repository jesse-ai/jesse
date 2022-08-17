from .BinanceMain import BinanceMain
from jesse.enums import exchanges


class BinancePerpetualFutures(BinanceMain):
    def __init__(self) -> None:
        from .BinanceSpot import BinanceSpot

        super().__init__(
            name=exchanges.BINANCE_PERPETUAL_FUTURES,
            rest_endpoint='https://fapi.binance.com/fapi/v1/klines',
            backup_exchange_class=BinanceSpot
        )
