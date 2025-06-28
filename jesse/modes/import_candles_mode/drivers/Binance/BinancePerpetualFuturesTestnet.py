from .BinanceMain import BinanceMain
from jesse.enums import Exchanges


class BinancePerpetualFuturesTestnet(BinanceMain):
    def __init__(self) -> None:
        from .BinanceSpot import BinanceSpot

        super().__init__(
            name=Exchanges.BINANCE_PERPETUAL_FUTURES_TESTNET,
            rest_endpoint='https://testnet.binancefuture.com/fapi',
            backup_exchange_class=BinanceSpot
        )
