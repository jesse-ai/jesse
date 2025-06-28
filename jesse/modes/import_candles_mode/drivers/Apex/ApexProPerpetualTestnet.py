from .ApexProMain import ApexProMain
from jesse.enums import Exchanges


class ApexProPerpetualTestnet(ApexProMain):
    def __init__(self) -> None:
        super().__init__(
            name=Exchanges.APEX_PRO_PERPETUAL_TESTNET.value,
            rest_endpoint='https://testnet.pro.apex.exchange/api/v2'
        )
