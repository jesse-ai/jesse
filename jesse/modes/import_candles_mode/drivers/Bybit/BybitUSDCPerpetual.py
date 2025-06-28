from .BybitMain import BybitMain
from jesse.enums import Exchanges


class BybitUSDCPerpetual(BybitMain):
    def __init__(self) -> None:
        super().__init__(
            name=Exchanges.BYBIT_USDC_PERPETUAL.value,
            rest_endpoint='https://api.bybit.com',
            category='linear',
        )
