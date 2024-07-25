from .BitgetUSDTPerpetualMain import BitgetUSDTPerpetualMain
from jesse.enums import exchanges


class BitgetUSDTPerpetual(BitgetUSDTPerpetualMain):
    def __init__(self) -> None:
        super().__init__(
            name=exchanges.BITGET_USDT_PERPETUAL,
            endpoint='https://api.bitget.com'
        )
