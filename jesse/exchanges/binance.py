import requests
import time
import hmac
import hashlib
import os
from dotenv import load_dotenv

load_dotenv()

BINANCE_BASE = "https://api.binance.com"

API_KEY = os.getenv("BINANCE_API_KEY")
SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")


def get_headers():
    return {
        "X-MBX-APIKEY": API_KEY
    }


def _sign(params):
    query = '&'.join([f"{k}={v}" for k, v in params.items()])
    signature = hmac.new(SECRET_KEY.encode(), query.encode(),
                         hashlib.sha256).hexdigest()
    return query + f"&signature={signature}"


def get_balance():
    ts = int(time.time() * 1000)
    params = {
        "timestamp": ts
    }
    signed = _sign(params)
    r = requests.get(
        f"{BINANCE_BASE}/api/v3/account?{signed}", headers=get_headers())
    return r.json()


def get_price(symbol="BTCUSDT"):
    r = requests.get(f"{BINANCE_BASE}/api/v3/ticker/price",
                     params={"symbol": symbol})
    return float(r.json()['price'])


def place_order(symbol, side, qty, order_type="MARKET"):
    ts = int(time.time() * 1000)
    params = {
        "symbol": symbol,
        "side": side.upper(),
        "type": order_type,
        "quantity": qty,
        "timestamp": ts
    }
    signed = _sign(params)
    r = requests.post(
        f"{BINANCE_BASE}/api/v3/order?{signed}", headers=get_headers())
    return r.json()
