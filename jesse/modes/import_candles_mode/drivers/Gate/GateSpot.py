from .GateSpotMain import GateSpotMain
from jesse.enums import Exchanges


class GateSpot(GateSpotMain):
    def __init__(self) -> None:
        super().__init__(
            name=Exchanges.GATE_SPOT,
            rest_endpoint='https://api.gateio.ws/api/v4/spot'
        )
