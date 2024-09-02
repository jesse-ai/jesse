from .GateMain import GateMain
from jesse.enums import exchanges


class GatePerpetualFutures(GateMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.GATE_PERPETUAL_FUTURES,
            rest_endpoint='https://api.gateio.ws/api'
        )
