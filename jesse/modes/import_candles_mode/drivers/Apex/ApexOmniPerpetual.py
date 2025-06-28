from .ApexProMain import ApexProMain
from jesse.enums import Exchanges


class ApexOmniPerpetual(ApexProMain):
    def __init__(self) -> None:
        super().__init__(
            name=Exchanges.APEX_OMNI_PERPETUAL,
            rest_endpoint='https://omni.apex.exchange/api/v3'
        )
