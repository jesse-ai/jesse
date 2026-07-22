from .ApexOmniPerpetualMain import ApexOmniPerpetualMain
from jesse.enums import exchanges


class ApexOmniPerpetual(ApexOmniPerpetualMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.APEX_OMNI_PERPETUAL,
            rest_endpoint='https://omni.apex.exchange/api/v3'
        )
