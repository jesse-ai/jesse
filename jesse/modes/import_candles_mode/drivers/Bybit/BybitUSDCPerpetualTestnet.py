from .BybitMain import BybitMain
from jesse.enums import exchanges


class BybitUSDCPerpetualTestnet(BybitMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.BYBIT_USDC_PERPETUAL_TESTNET,
            rest_endpoint='https://api-testnet.bybit.com',
            category='linear',
        )
