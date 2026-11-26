from jesse.enums import exchanges
from .AlpacaStocksMain import AlpacaStocksMain
from .alpaca_utils import LIVE_TRADING_ENDPOINT


class AlpacaStocksCash(AlpacaStocksMain):
    def __init__(self) -> None:
        super().__init__(name=exchanges.ALPACA_STOCKS_CASH, trading_endpoint=LIVE_TRADING_ENDPOINT)
