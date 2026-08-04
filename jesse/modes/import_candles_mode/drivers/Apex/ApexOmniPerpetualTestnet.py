from .ApexOmniPerpetualMain import ApexOmniPerpetualMain
from jesse.enums import exchanges


class ApexOmniPerpetualTestnet(ApexOmniPerpetualMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.APEX_OMNI_PERPETUAL_TESTNET,
            rest_endpoint='https://testnet.omni.apex.exchange/api/v3'
        )
