from .ApexProMain import ApexProMain
from jesse.enums import exchanges


class ApexProPerpetualTestnet(ApexProMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.APEX_PRO_PERPETUAL_TESTNET,
            rest_endpoint='https://testnet.pro.apex.exchange/api/v2'
        )
