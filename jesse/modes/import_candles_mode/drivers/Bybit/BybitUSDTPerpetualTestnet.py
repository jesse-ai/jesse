from .BybitMain import BybitMain
from jesse.enums import exchanges


class BybitUSDTPerpetualTestnet(BybitMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.BYBIT_USDT_PERPETUAL_TESTNET,
            rest_endpoint='https://api-testnet.bybit.com',
            category='linear',
        )
