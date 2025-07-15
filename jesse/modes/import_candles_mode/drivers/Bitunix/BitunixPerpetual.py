from .BitunixMain import BitunixMain
from jesse.enums import exchanges


class BitunixPerpetual(BitunixMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.BITUNIX_PERPETUAL,
            rest_endpoint='https://fapi.bitunix.com/api/v1/futures'
        )
