from .DydxPerpetualMain import DydxPerpetualMain
from jesse.enums import exchanges


class DydxPerpetualTestnet(DydxPerpetualMain):
    def __init__(self) -> None:
        from jesse.modes.import_candles_mode.drivers.DyDx.DydxPerpetual import DydxPerpetual
        super().__init__(
            name=exchanges.DYDX_PERPETUAL_TESTNET,
            rest_endpoint='https://api.stage.dydx.exchange',
            backup_exchange_class=DydxPerpetual
        )
