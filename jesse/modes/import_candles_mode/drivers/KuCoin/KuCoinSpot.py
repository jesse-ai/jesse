from .KuCoinMain import KuCoinMain
from jesse.enums import exchanges


class KuCoinSpot(KuCoinMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.KUCOIN_SPOT,
            rest_endpoint='https://api.kucoin.com',
            backup_exchange_class=None
        )
