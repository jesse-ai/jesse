from .GateUSDTMain import GateUSDTMain
from jesse.enums import Exchanges


class GateUSDTPerpetual(GateUSDTMain):
    def __init__(self) -> None:
        super().__init__(
            name=Exchanges.GATE_USDT_PERPETUAL,
            rest_endpoint='https://api.gateio.ws/api/v4/futures'
        )
