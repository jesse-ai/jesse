from .GateUSDTMain import GateUSDTMain
from jesse.enums import exchanges


class GateSpot(GateUSDTMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.GATE_SPOT,
            rest_endpoint='https://api.gateio.ws/api/v4/spot'
        )
