from .DydxPerpetualMain import DydxPerpetualMain
from jesse.enums import exchanges


class DydxPerpetual(DydxPerpetualMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.DYDX_PERPETUAL,
            rest_endpoint='https://api.dydx.exchange',
        )
