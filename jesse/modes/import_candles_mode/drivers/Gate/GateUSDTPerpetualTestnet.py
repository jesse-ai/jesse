from .GateUSDTMain import GateUSDTMain
from jesse.enums import exchanges


class GateUSDTPerpetualTestnet(GateUSDTMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.GATE_USDT_PERPETUAL_TESTNET,
            rest_endpoint='https://fx-api-testnet.gateio.ws/api/v4/futures'
        )
