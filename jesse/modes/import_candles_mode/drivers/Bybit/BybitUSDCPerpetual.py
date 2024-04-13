from .BybitMain import BybitMain
from jesse.enums import exchanges


class BybitUSDCPerpetual(BybitMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.BYBIT_USDC_PERPETUAL,
            rest_endpoint='https://api.bybit.com',
            category='linear',
        )
