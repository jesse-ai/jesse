from .BybitMain import BybitMain
from jesse.enums import Exchanges


class BybitSpot(BybitMain):
    def __init__(self) -> None:
        super().__init__(
            name=Exchanges.BYBIT_SPOT,
            rest_endpoint='https://api.bybit.com',
            category='spot',
        )
