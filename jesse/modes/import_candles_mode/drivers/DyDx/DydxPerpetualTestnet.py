from .DydxPerpetualMain import DydxPerpetualMain
from jesse.enums import exchanges


class DydxPerpetualTestnet(DydxPerpetualMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.DYDX_PERPETUAL_TESTNET,
            rest_endpoint='https://api.stage.dydx.exchange',
        )
