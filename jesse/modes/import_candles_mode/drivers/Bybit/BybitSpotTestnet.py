from .BybitMain import BybitMain
from jesse.enums import exchanges


class BybitSpotTestnet(BybitMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.BYBIT_SPOT_TESTNET,
            rest_endpoint='https://api-testnet.bybit.com',
            category='spot',
        )
