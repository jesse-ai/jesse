from .KuCoinSpotMain import KuCoinSpotMain
from jesse.enums import exchanges


class KuCoinSpot(KuCoinSpotMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.KUCOIN_SPOT,
            rest_endpoint='https://api.kucoin.com',
        )
