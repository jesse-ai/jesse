import time
import logging
import requests
import numpy as np
from typing import List, Optional, Tuple
from datetime import datetime, timedelta

from binance.client import Client as BinanceClient
from kucoin.client import Market as KucoinMarketClient
from jesse import exchanges

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load API keys securely from environment variables
BINANCE_API_KEY = exchanges.env("BINANCE_API_KEY")
BINANCE_SECRET = exchanges.env("BINANCE_SECRET")

# Initialize clients with error handling
try:
    binance_client = BinanceClient(
        api_key=BINANCE_API_KEY,
        api_secret=BINANCE_SECRET
    ) if BINANCE_API_KEY and BINANCE_SECRET else None
except Exception as e:
    logger.error(f"Failed to initialize Binance client: {e}")
    binance_client = None

try:
    kucoin_client = KucoinMarketClient()
except Exception as e:
    logger.error(f"Failed to initialize KuCoin client: {e}")
    kucoin_client = None


def fetch_binance_ohlcv(
    symbol: str = "BTCUSDT",
    interval: str = "1m",
    limit: int = 500,
    use_client: bool = False
) -> Optional[np.ndarray]:
    """
    Fetch historical OHLCV candles from Binance.

    Args:
        symbol: Trading pair symbol (e.g., "BTCUSDT")
        interval: Time interval (1m, 5m, 15m, 1h, 1d, etc.)
        limit: Number of candles to fetch (max 1000)
        use_client: Whether to use authenticated client or REST API

    Returns:
        numpy array with columns: [timestamp, open, close, high, low, volume]
        or None if failed
    """
    try:
        # Validate inputs
        if limit > 1000:
            logger.warning("Binance limit cannot exceed 1000, setting to 1000")
            limit = 1000

        if use_client and binance_client:
            # Use authenticated client (more reliable for high-frequency requests)
            logger.info(f"Fetching {symbol} data via Binance client")
            klines = binance_client.get_historical_klines(
                symbol, interval, limit=limit
            )
            data = klines
        else:
            # Use public REST API
            logger.info(f"Fetching {symbol} data via Binance REST API")
            url = "https://api.binance.com/api/v3/klines"
            params = {
                "symbol": symbol,
                "interval": interval,
                "limit": limit
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

        if not data:
            logger.error("No data received from Binance")
            return None

        # Parse candles with proper error handling
        candles = []
        for i, candle in enumerate(data):
            try:
                # Binance format: [timestamp, open, high, low, close, volume, ...]
                parsed_candle = [
                    int(candle[0]),      # timestamp
                    float(candle[1]),    # open
                    float(candle[4]),    # close
                    float(candle[2]),    # high
                    float(candle[3]),    # low
                    float(candle[5])     # volume
                ]
                candles.append(parsed_candle)
            except (ValueError, IndexError) as e:
                logger.warning(f"Failed to parse candle {i}: {e}")
                continue

        if not candles:
            logger.error("No valid candles parsed")
            return None

        logger.info(
            f"Successfully fetched {len(candles)} candles from Binance")
        return np.array(candles)

    except requests.exceptions.RequestException as e:
        logger.error(f"Network error fetching Binance data: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching Binance data: {e}")
        return None


def fetch_kucoin_ohlcv(
    symbol: str = "BTC-USDT",
    interval: str = "1min",
    limit: int = 500
) -> Optional[List[List]]:
    """
    Fetch historical OHLCV candles from KuCoin.

    Args:
        symbol: Trading pair symbol with dash (e.g., "BTC-USDT")
        interval: Time interval (1min, 5min, 15min, 1hour, 1day, etc.)
        limit: Number of candles to fetch

    Returns:
        List of candles: [timestamp, open, close, high, low, volume]
        or None if failed
    """
    if not kucoin_client:
        logger.error("KuCoin client not initialized")
        return None

    try:
        # Calculate time range
        current_time = int(time.time())
        interval_seconds = _parse_kucoin_interval(interval)
        start_time = current_time - (limit * interval_seconds)

        logger.info(f"Fetching {symbol} data from KuCoin")

        # Fetch data from KuCoin
        response = kucoin_client.get_kline(
            symbol=symbol,
            kline_type=interval,
            startAt=start_time,
            endAt=current_time
        )

        if not response or 'data' not in response:
            logger.error("Invalid response from KuCoin API")
            return None

        raw_data = response['data']

        if not raw_data:
            logger.error("No data received from KuCoin")
            return None

        # KuCoin returns data in reverse chronological order
        raw_data.reverse()

        # Parse candles with error handling
        candles = []
        for i, kline in enumerate(raw_data):
            try:
                # KuCoin format: [timestamp, open, close, high, low, volume, turnover]
                parsed_candle = [
                    int(kline[0]),       # timestamp
                    float(kline[1]),     # open
                    float(kline[2]),     # close
                    float(kline[3]),     # high
                    float(kline[4]),     # low
                    float(kline[5])      # volume
                ]
                candles.append(parsed_candle)
            except (ValueError, IndexError, TypeError) as e:
                logger.warning(f"Failed to parse KuCoin candle {i}: {e}")
                continue

        if not candles:
            logger.error("No valid candles parsed from KuCoin")
            return None

        # Limit results if we got more than requested
        candles = candles[-limit:] if len(candles) > limit else candles

        logger.info(f"Successfully fetched {len(candles)} candles from KuCoin")
        return candles

    except Exception as e:
        logger.error(f"Error fetching KuCoin data: {e}")
        return None


def _parse_kucoin_interval(interval: str) -> int:
    """Convert KuCoin interval string to seconds."""
    interval_map = {
        '1min': 60,
        '3min': 180,
        '5min': 300,
        '15min': 900,
        '30min': 1800,
        '1hour': 3600,
        '2hour': 7200,
        '4hour': 14400,
        '6hour': 21600,
        '8hour': 28800,
        '12hour': 43200,
        '1day': 86400,
        '1week': 604800
    }
    return interval_map.get(interval, 60)  # Default to 1 minute


def compare_exchanges_data(
    symbol_binance: str = "BTCUSDT",
    symbol_kucoin: str = "BTC-USDT",
    interval: str = "1m",
    limit: int = 100
) -> None:
    """
    Fetch and compare data from both exchanges.

    Args:
        symbol_binance: Binance symbol format
        symbol_kucoin: KuCoin symbol format (with dash)
        interval: Time interval
        limit: Number of candles
    """
    print(f"\n=== Comparing {symbol_binance} data ===")

    # Map Binance interval to KuCoin interval
    kucoin_interval = interval.replace('m', 'min').replace(
        'h', 'hour').replace('d', 'day')

    # Fetch from both exchanges
    binance_data = fetch_binance_ohlcv(symbol_binance, interval, limit)
    kucoin_data = fetch_kucoin_ohlcv(symbol_kucoin, kucoin_interval, limit)

    # Display results
    if binance_data is not None:
        print(f"Binance: {len(binance_data)} candles")
        if len(binance_data) > 0:
            latest = binance_data[-1]
            print(
                f"  Latest: {datetime.fromtimestamp(latest[0]/1000)} | O:{latest[1]:.2f} C:{latest[2]:.2f} H:{latest[3]:.2f} L:{latest[4]:.2f} V:{latest[5]:.2f}")
    else:
        print("Binance: Failed to fetch data")

    if kucoin_data is not None:
        print(f"KuCoin: {len(kucoin_data)} candles")
        if len(kucoin_data) > 0:
            latest = kucoin_data[-1]
            print(
                f"  Latest: {datetime.fromtimestamp(latest[0])} | O:{latest[1]:.2f} C:{latest[2]:.2f} H:{latest[3]:.2f} L:{latest[4]:.2f} V:{latest[5]:.2f}")
    else:
        print("KuCoin: Failed to fetch data")


# Example usage and testing
if __name__ == "__main__":
    # Test both exchanges
    compare_exchanges_data("BTCUSDT", "BTC-USDT", "1m", 10)

    # Test individual functions
    print("\n=== Individual Tests ===")

    # Test Binance
    binance_candles = fetch_binance_ohlcv("ETHUSDT", "5m", 50)
    if binance_candles is not None:
        print(f"Binance ETH: {binance_candles.shape}")

    # Test KuCoin
    kucoin_candles = fetch_kucoin_ohlcv("ETH-USDT", "5min", 50)
    if kucoin_candles is not None:
        print(f"KuCoin ETH: {len(kucoin_candles)} candles")
