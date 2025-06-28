from .BybitMain import BybitMain
from jesse.enums import Exchanges


class BybitUSDTPerpetual(BybitMain):
    def __init__(self) -> None:
        super().__init__(
            name=Exchanges.BYBIT_USDT_PERPETUAL,
            rest_endpoint='https://api.bybit.com',
            category='linear',
        )
