from jesse.enums import exchanges
from .AlpacaStocksMain import AlpacaStocksMain
from .alpaca_utils import PAPER_TRADING_ENDPOINT


class AlpacaStocksMarginPaper(AlpacaStocksMain):
    def __init__(self) -> None:
        super().__init__(name=exchanges.ALPACA_STOCKS_MARGIN_PAPER, trading_endpoint=PAPER_TRADING_ENDPOINT)
