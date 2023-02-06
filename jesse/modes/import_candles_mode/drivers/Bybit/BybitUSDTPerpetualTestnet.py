from .BybitUSDTPerpetualMain import BybitUSDTPerpetualMain
from jesse.enums import exchanges


class BybitUSDTPerpetualTestnet(BybitUSDTPerpetualMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.BYBIT_USDT_PERPETUAL_TESTNET,
            rest_endpoint='https://api-testnet.bybit.com',
        )
