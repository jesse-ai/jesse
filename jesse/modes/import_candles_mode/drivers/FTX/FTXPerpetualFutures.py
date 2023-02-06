from .FTXMain import FTXMain
from jesse.enums import exchanges


class FTXPerpetualFutures(FTXMain):
    def __init__(self) -> None:
        # import here instead of the top of the file to prevent the possible circular imports issue
        from jesse.modes.import_candles_mode.drivers.FTX.FTXSpot import FTXSpot

        super().__init__(
            name=exchanges.FTX_PERPETUAL_FUTURES,
            rest_endpoint='https://ftx.com',
            backup_exchange_class=FTXSpot
        )
