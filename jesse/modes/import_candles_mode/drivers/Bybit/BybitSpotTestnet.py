from .BybitMain import BybitMain
from jesse.enums import Exchanges


class BybitSpotTestnet(BybitMain):
    def __init__(self) -> None:
        super().__init__(
            name=Exchanges.BYBIT_SPOT_TESTNET.value,
            rest_endpoint='https://api-testnet.bybit.com',
            category='spot',
        )
