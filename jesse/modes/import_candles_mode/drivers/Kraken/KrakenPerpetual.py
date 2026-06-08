from .KrakenPerpetualMain import KrakenPerpetualMain
from jesse.enums import exchanges


class KrakenPerpetual(KrakenPerpetualMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.KRAKEN_PERPETUAL,
            rest_endpoint='https://futures.kraken.com',
        )
