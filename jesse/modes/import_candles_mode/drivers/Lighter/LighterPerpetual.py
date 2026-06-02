from .LighterMain import LighterMain
from jesse.enums import exchanges


class LighterPerpetual(LighterMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.LIGHTER_PERPETUAL,
            rest_endpoint='https://mainnet.zklighter.elliot.ai',
        )
