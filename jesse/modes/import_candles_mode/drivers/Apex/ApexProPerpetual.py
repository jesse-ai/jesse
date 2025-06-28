from .ApexProMain import ApexProMain
from jesse.enums import Exchanges


class ApexProPerpetual(ApexProMain):
    def __init__(self) -> None:
        super().__init__(
            name=Exchanges.APEX_PRO_PERPETUAL,
            rest_endpoint='https://pro.apex.exchange/api/v2'
        )
