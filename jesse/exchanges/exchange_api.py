import os
import time
import numpy as np
from dotenv import load_dotenv
from binance.client import Client as BinanceClient
from kucoin.client import Client as KucoinClient

load_dotenv()

# --- Binance Setup ---
binance = BinanceClient(
    api_key=os.getenv("BINANCE_API_KEY"),
    api_secret=os.getenv("BINANCE_SECRET_KEY")
)

# --- KuCoin Setup ---
kucoin = KucoinClient(
    api_key=os.getenv("KUCOIN_API_KEY"),
    api_secret=os.getenv("KUCOIN_SECRET_KEY"),
    passphrase=os.getenv("KUCOIN_PASSPHRASE")
)


def fetch_binance_candles(symbol="BTCUSDT", interval="1m", limit=100):
    klines = binance.get_klines(symbol=symbol, interval=interval, limit=limit)
    return np.array([
        [
            int(k[0]), float(k[1]), float(k[4]),  # timestamp, open, close
            float(k[2]), float(k[3]), float(k[5])  # high, low, volume
        ] for k in klines
    ])


def fetch_kucoin_candles(symbol="BTC-USDT", interval="1min"):
    candles = kucoin.get_kline_data(symbol, kline_type=interval)
    return np.array([
        [
            # timestamp, open, close
            int(k[0] * 1000), float(k[1]), float(k[2]),
            float(k[3]), float(k[4]), float(k[5])       # high, low, volume
        ] for k in candles
    ][::-1])
