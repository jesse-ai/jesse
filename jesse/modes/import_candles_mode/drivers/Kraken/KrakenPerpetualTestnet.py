from .KrakenPerpetualMain import KrakenPerpetualMain
from jesse.enums import exchanges


class KrakenPerpetualTestnet(KrakenPerpetualMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.KRAKEN_PERPETUAL_TESTNET,
            rest_endpoint='https://demo-futures.kraken.com',
        )
