from .HyperliquidPerpetualMain import HyperliquidPerpetualMain
from jesse.enums import exchanges


class HyperliquidPerpetual(HyperliquidPerpetualMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.HYPERLIQUID_PERPETUAL,
            rest_endpoint='https://api.hyperliquid.xyz/info'
        )
