import requests
import time
import hmac
import base64
import hashlib
import os
from dotenv import load_dotenv

load_dotenv()

KUCOIN_BASE = "https://api.kucoin.com"

API_KEY = os.getenv("KUCOIN_API_KEY")
SECRET_KEY = os.getenv("KUCOIN_SECRET_KEY")
PASSPHRASE = os.getenv("KUCOIN_PASSPHRASE")


def get_headers(method, endpoint, body=''):
    now = int(time.time() * 1000)
    str_to_sign = f'{now}{method}{endpoint}{body}'
    signature = base64.b64encode(
        hmac.new(SECRET_KEY.encode(), str_to_sign.encode(),
                 hashlib.sha256).digest()
    )
    passphrase = base64.b64encode(
        hmac.new(SECRET_KEY.encode(), PASSPHRASE.encode(),
                 hashlib.sha256).digest()
    )

    return {
        "KC-API-KEY": API_KEY,
        "KC-API-SIGN": signature.decode(),
        "KC-API-TIMESTAMP": str(now),
        "KC-API-PASSPHRASE": passphrase.decode(),
        "KC-API-KEY-VERSION": "2",
        "Content-Type": "application/json"
    }


def get_accounts():
    endpoint = "/api/v1/accounts"
    headers = get_headers("GET", endpoint)
    r = requests.get(KUCOIN_BASE + endpoint, headers=headers)
    return r.json()


def get_price(symbol="BTC-USDT"):
    endpoint = f"/api/v1/market/orderbook/level1?symbol={symbol}"
    r = requests.get(KUCOIN_BASE + endpoint)
    return float(r.json()['data']['price'])


def place_order(symbol, side, qty, order_type="market"):
    endpoint = "/api/v1/orders"
    body = {
        "clientOid": str(int(time.time() * 1000)),
        "side": side,
        "symbol": symbol,
        "type": order_type,
        "size": str(qty)
    }
    import json
    headers = get_headers("POST", endpoint, json.dumps(body))
    r = requests.post(KUCOIN_BASE + endpoint, headers=headers, json=body)
    return r.json()
