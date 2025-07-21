from .BloFinMain import BloFinMain
from jesse.enums import exchanges


class BloFinPerpetual(BloFinMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.BLOFIN_PERPETUAL,
            rest_endpoint='https://openapi.blofin.com/api/v1',
        )
