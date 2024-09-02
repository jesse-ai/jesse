from .GateMain import GateMain
from jesse.enums import exchanges


class GatePerpetualFuturesTestnet(GateMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.GATE_PERPETUAL_FUTURES_TESTNET,
            rest_endpoint='https://fx-api-testnet.gateio.ws/api/v4/futures'
        )
