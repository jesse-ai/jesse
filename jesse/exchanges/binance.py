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

if not API_KEY or not SECRET_KEY:
    raise Exception("API keys not found. Check your .env file")


def get_headers():
    return {
        "X-MBX-APIKEY": API_KEY
    }


def _sign(params):
    query = '&'.join([f"{k}={v}" for k, v in params.items()])
    signature = hmac.new(SECRET_KEY.encode(), query.encode(), hashlib.sha256).hexdigest()
    return query + f"&signature={signature}"


def get_balance():
    ts = int(time.time() * 1000)
    params = {
        "timestamp": ts,
        "recvWindow": 5000
    }
    signed = _sign(params)
    r = requests.get(f"{BINANCE_BASE}/api/v3/account?{signed}", headers=get_headers())
    if r.status_code != 200:
        print("Error:", r.text)
        return None
    return r.json()


def get_price(symbol="BTCUSDT"):
    r = requests.get(f"{BINANCE_BASE}/api/v3/ticker/price", params={"symbol": symbol.upper()})
    if r.status_code != 200:
        print("Error:", r.text)
        return None
    return float(r.json()['price'])


def place_order(symbol, side, qty, order_type="MARKET"):
    ts = int(time.time() * 1000)
    params = {
        "symbol": symbol.upper(),
        "side": side.upper(),
        "type": order_type,
        "timestamp": ts,
        "recvWindow": 5000
    }

    # Market order logic
    if order_type == "MARKET":
        if side.upper() == "BUY":
            params["quoteOrderQty"] = qty  # e.g. 50 USDT
        else:
            params["quantity"] = qty       # e.g. 0.001 BTC
    else:
        params["quantity"] = qty

    signed = _sign(params)
    r = requests.post(f"{BINANCE_BASE}/api/v3/order?{signed}", headers=get_headers())
    if r.status_code != 200:
        print("Order Error:", r.text)
        return None
    return r.json()
