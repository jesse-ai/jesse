from jesse.enums import Exchanges
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
from jesse.modes.import_candles_mode.drivers.Bybit.BybitSpotTestnet import BybitSpotTestnet
from jesse.modes.import_candles_mode.drivers.Bybit.BybitSpot import BybitSpot
from jesse.modes.import_candles_mode.drivers.Apex.ApexProPerpetualTestnet import ApexProPerpetualTestnet
from jesse.modes.import_candles_mode.drivers.Apex.ApexProPerpetual import ApexProPerpetual
from jesse.modes.import_candles_mode.drivers.Apex.ApexOmniPerpetualTestnet import ApexOmniPerpetualTestnet
from jesse.modes.import_candles_mode.drivers.Apex.ApexOmniPerpetual import ApexOmniPerpetual
from jesse.modes.import_candles_mode.drivers.Gate.GateUSDTPerpetual import GateUSDTPerpetual
from jesse.modes.import_candles_mode.drivers.Gate.GateSpot import GateSpot
from jesse.modes.import_candles_mode.drivers.Hyperliquid.HyperliquidPerpetual import HyperliquidPerpetual
from jesse.modes.import_candles_mode.drivers.Hyperliquid.HyperliquidPerpetualTestnet import HyperliquidPerpetualTestnet


drivers = {
    # Perpetual Futures
    Exchanges.BINANCE_PERPETUAL_FUTURES.value: BinancePerpetualFutures,
    Exchanges.BINANCE_PERPETUAL_FUTURES_TESTNET.value: BinancePerpetualFuturesTestnet,
    Exchanges.BITFINEX_SPOT.value: BitfinexSpot,
    Exchanges.COINBASE_SPOT.value: CoinbaseSpot,
    Exchanges.BYBIT_USDT_PERPETUAL.value: BybitUSDTPerpetual,
    Exchanges.BYBIT_USDT_PERPETUAL_TESTNET.value: BybitUSDTPerpetualTestnet,
    Exchanges.BYBIT_USDC_PERPETUAL.value: BybitUSDCPerpetual,
    Exchanges.BYBIT_USDC_PERPETUAL_TESTNET.value: BybitUSDCPerpetualTestnet,
    Exchanges.APEX_PRO_PERPETUAL_TESTNET.value: ApexProPerpetualTestnet,
    Exchanges.APEX_PRO_PERPETUAL.value: ApexProPerpetual,
    Exchanges.APEX_OMNI_PERPETUAL_TESTNET.value: ApexOmniPerpetualTestnet,
    Exchanges.APEX_OMNI_PERPETUAL.value: ApexOmniPerpetual,
    Exchanges.GATE_USDT_PERPETUAL.value: GateUSDTPerpetual,
    Exchanges.GATE_SPOT.value: GateSpot,
    Exchanges.HYPERLIQUID_PERPETUAL.value: HyperliquidPerpetual,
    Exchanges.HYPERLIQUID_PERPETUAL_TESTNET.value: HyperliquidPerpetualTestnet,
    # Spot
    Exchanges.BINANCE_SPOT.value: BinanceSpot,
    Exchanges.BINANCE_US_SPOT.value: BinanceUSSpot,
    Exchanges.BYBIT_SPOT_TESTNET.value: BybitSpotTestnet,
    Exchanges.BYBIT_SPOT.value: BybitSpot,
}


driver_names = list(drivers.keys())
