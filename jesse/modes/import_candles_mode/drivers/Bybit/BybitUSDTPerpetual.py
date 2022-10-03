from .BybitUSDTPerpetualMain import BybitUSDTPerpetualMain
from jesse.enums import exchanges


class BybitUSDTPerpetual(BybitUSDTPerpetualMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.BYBIT_USDT_PERPETUAL,
            rest_endpoint='https://api.bytick.com',
        )
