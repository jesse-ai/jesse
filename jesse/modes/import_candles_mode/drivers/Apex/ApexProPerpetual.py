from .ApexProMain import ApexProMain
from jesse.enums import exchanges


class ApexProPerpetual(ApexProMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.APEX_PRO_PERPETUAL,
            rest_endpoint='https://pro.apex.exchange/api'
        )
