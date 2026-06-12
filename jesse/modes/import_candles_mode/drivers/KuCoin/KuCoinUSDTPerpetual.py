from .KuCoinFuturesMain import KuCoinFuturesMain
from jesse.enums import exchanges


class KuCoinUSDTPerpetual(KuCoinFuturesMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.KUCOIN_USDT_PERPETUAL,
            rest_endpoint='https://api-futures.kucoin.com',
        )
