from .KrakenSpotMain import KrakenSpotMain
from jesse.enums import exchanges


class KrakenSpot(KrakenSpotMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.KRAKEN_SPOT,
            rest_endpoint='https://api.kraken.com',
        )
