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
    Exchanges.BINANCE_PERPETUAL_FUTURES: BinancePerpetualFutures,
    Exchanges.BINANCE_PERPETUAL_FUTURES_TESTNET: BinancePerpetualFuturesTestnet,
    Exchanges.BITFINEX_SPOT: BitfinexSpot,
    Exchanges.COINBASE_SPOT: CoinbaseSpot,
    Exchanges.BYBIT_USDT_PERPETUAL: BybitUSDTPerpetual,
    Exchanges.BYBIT_USDT_PERPETUAL_TESTNET: BybitUSDTPerpetualTestnet,
    Exchanges.BYBIT_USDC_PERPETUAL: BybitUSDCPerpetual,
    Exchanges.BYBIT_USDC_PERPETUAL_TESTNET: BybitUSDCPerpetualTestnet,
    Exchanges.APEX_PRO_PERPETUAL_TESTNET: ApexProPerpetualTestnet,
    Exchanges.APEX_PRO_PERPETUAL: ApexProPerpetual,
    Exchanges.APEX_OMNI_PERPETUAL_TESTNET: ApexOmniPerpetualTestnet,
    Exchanges.APEX_OMNI_PERPETUAL: ApexOmniPerpetual,
    Exchanges.GATE_USDT_PERPETUAL: GateUSDTPerpetual,
    Exchanges.GATE_SPOT: GateSpot,
    Exchanges.HYPERLIQUID_PERPETUAL: HyperliquidPerpetual,
    Exchanges.HYPERLIQUID_PERPETUAL_TESTNET: HyperliquidPerpetualTestnet,
    # Spot
    Exchanges.BINANCE_SPOT: BinanceSpot,
    Exchanges.BINANCE_US_SPOT: BinanceUSSpot,
    Exchanges.BYBIT_SPOT_TESTNET: BybitSpotTestnet,
    Exchanges.BYBIT_SPOT: BybitSpot,
}


driver_names = list(drivers.keys())
