from pydoc import locate
from jesse.enums import exchanges
from jesse.modes.import_candles_mode.drivers.Binance.BinanceSpot import BinanceSpot
from jesse.modes.import_candles_mode.drivers.Binance.BinanceUSSpot import BinanceUSSpot
from jesse.modes.import_candles_mode.drivers.Binance.BinancePerpetualFutures import BinancePerpetualFutures
from jesse.modes.import_candles_mode.drivers.Bitfinex.BitfinexSpot import BitfinexSpot
from jesse.modes.import_candles_mode.drivers.Coinbase.CoinbaseSpot import CoinbaseSpot
from jesse.modes.import_candles_mode.drivers.Binance.BinancePerpetualFuturesTestnet import BinancePerpetualFuturesTestnet
from jesse.modes.import_candles_mode.drivers.Bybit.BybitUSDTPerpetual import BybitUSDTPerpetual
from jesse.modes.import_candles_mode.drivers.Bybit.BybitUSDTPerpetualTestnet import BybitUSDTPerpetualTestnet
from jesse.modes.import_candles_mode.drivers.Bybit.BybitUSDCPerpetual import BybitUSDCPerpetual
from jesse.modes.import_candles_mode.drivers.Bybit.BybitUSDCPerpetualTestnet import BybitUSDCPerpetualTestnet
from jesse.modes.import_candles_mode.drivers.FTX.FTXPerpetualFutures import FTXPerpetualFutures
from jesse.modes.import_candles_mode.drivers.FTX.FTXSpot import FTXSpot
from jesse.modes.import_candles_mode.drivers.FTX.FTXUSSpot import FTXUSSpot
from jesse.modes.import_candles_mode.drivers.Bitget.BitgetUSDTPerpetual import BitgetUSDTPerpetual
from jesse.modes.import_candles_mode.drivers.Bitget.BitgetUSDTPerpetualTestnet import BitgetUSDTPerpetualTestnet
from jesse.modes.import_candles_mode.drivers.DyDx.DydxPerpetual import DydxPerpetual
from jesse.modes.import_candles_mode.drivers.DyDx.DydxPerpetualTestnet import DydxPerpetualTestnet
from jesse.modes.import_candles_mode.drivers.Bybit.BybitSpotTestnet import BybitSpotTestnet
from jesse.modes.import_candles_mode.drivers.Bybit.BybitSpot import BybitSpot
from jesse.modes.import_candles_mode.drivers.Apex.ApexProPerpetualTestnet import ApexProPerpetualTestnet
from jesse.modes.import_candles_mode.drivers.Apex.ApexProPerpetual import ApexProPerpetual


drivers = {
    # Perpetual Futures
    exchanges.BINANCE_PERPETUAL_FUTURES: BinancePerpetualFutures,
    exchanges.BINANCE_PERPETUAL_FUTURES_TESTNET: BinancePerpetualFuturesTestnet,
    exchanges.BITFINEX_SPOT: BitfinexSpot,
    exchanges.COINBASE_SPOT: CoinbaseSpot,
    exchanges.BYBIT_USDT_PERPETUAL: BybitUSDTPerpetual,
    exchanges.BYBIT_USDT_PERPETUAL_TESTNET: BybitUSDTPerpetualTestnet,
    exchanges.BYBIT_USDC_PERPETUAL: BybitUSDCPerpetual,
    exchanges.BYBIT_USDC_PERPETUAL_TESTNET: BybitUSDCPerpetualTestnet,
    exchanges.FTX_PERPETUAL_FUTURES: FTXPerpetualFutures,
    exchanges.BITGET_USDT_PERPETUAL: BitgetUSDTPerpetual,
    exchanges.BITGET_USDT_PERPETUAL_TESTNET: BitgetUSDTPerpetualTestnet,
    exchanges.APEX_PRO_PERPETUAL_TESTNET: ApexProPerpetualTestnet,
    exchanges.APEX_PRO_PERPETUAL: ApexProPerpetual,

    # Spot
    exchanges.FTX_SPOT: FTXSpot,
    exchanges.FTX_US_SPOT: FTXUSSpot,
    exchanges.BINANCE_SPOT: BinanceSpot,
    exchanges.BINANCE_US_SPOT: BinanceUSSpot,
    exchanges.BYBIT_SPOT_TESTNET: BybitSpotTestnet,
    exchanges.BYBIT_SPOT: BybitSpot,

    # DEX
    exchanges.DYDX_PERPETUAL: DydxPerpetual,
    exchanges.DYDX_PERPETUAL_TESTNET: DydxPerpetualTestnet
}


driver_names = list(drivers.keys())
