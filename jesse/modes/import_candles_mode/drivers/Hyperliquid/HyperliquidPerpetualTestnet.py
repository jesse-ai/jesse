from .HyperliquidPerpetualMain import HyperliquidPerpetualMain
from jesse.enums import Exchanges


class HyperliquidPerpetualTestnet(HyperliquidPerpetualMain):
    def __init__(self) -> None:
        super().__init__(
            name=Exchanges.HYPERLIQUID_PERPETUAL_TESTNET.value,
            rest_endpoint='https://api.hyperliquid-testnet.xyz/info'
        )
