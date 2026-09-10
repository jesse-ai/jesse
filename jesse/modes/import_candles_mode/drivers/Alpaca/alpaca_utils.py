"""
Helpers shared by the Alpaca candle-import driver (jesse) and the Alpaca live driver (jesse-live).

Alpaca splits its API in two hosts: the trading API (``api.alpaca.markets`` / ``paper-api``) and
the market-data API (``data.alpaca.markets``), both authenticated with the same key pair sent as
plain headers. Paper and live keys are different key pairs but the data API accepts either.
"""
import os
from datetime import datetime, timezone

import requests

import jesse.helpers as jh
from jesse import exceptions

DATA_ENDPOINT = 'https://data.alpaca.markets'
PAPER_TRADING_ENDPOINT = 'https://paper-api.alpaca.markets'
LIVE_TRADING_ENDPOINT = 'https://api.alpaca.markets'
DATA_STREAM_ENDPOINT = 'wss://stream.data.alpaca.markets/v2'

# Alpaca serves any [1-59]Min, [1-23]Hour and 1Day bar natively, all clock-aligned in UTC, which is
# the same bucketing Jesse uses when it generates bigger timeframes from 1m.
_TIMEFRAME_TO_ALPACA = {
    '1m': '1Min', '3m': '3Min', '5m': '5Min', '15m': '15Min', '30m': '30Min', '45m': '45Min',
    '1h': '1Hour', '2h': '2Hour', '3h': '3Hour', '4h': '4Hour', '6h': '6Hour', '8h': '8Hour',
    '12h': '12Hour', '1D': '1Day',
}

# Free ("Basic") accounts may not read SIP bars younger than 15 minutes over REST and cannot stream
# SIP at all, so on that plan everything (warm-up, REST refresh, websocket) uses IEX for consistency.
FEED_IEX = 'iex'
FEED_SIP = 'sip'
SIP_RECENT_WINDOW_MINUTES = 15
_SIP_RECENCY_RESTRICTED_STATUS = 403

# Earliest 1-minute bar per feed (observed on 2026-09-04 for AAPL).
FEED_STARTING_TIMESTAMPS = {
    FEED_IEX: 1595808000000,  # 2020-07-27
    FEED_SIP: 1451606400000,  # 2016-01-01
}


def timeframe_to_alpaca(timeframe: str) -> str:
    try:
        return _TIMEFRAME_TO_ALPACA[timeframe]
    except KeyError as exc:
        raise ValueError(f'Timeframe "{timeframe}" is not supported by Alpaca') from exc


def alpaca_symbol(symbol: str) -> str:
    """Jesse 'BRK.B-USD' -> Alpaca 'BRK.B'. Dots are part of the ticker, so the dashless helper is not used."""
    return symbol.split('-')[0]


def jesse_symbol(alpaca_ticker: str) -> str:
    return f'{alpaca_ticker}-USD'


def rfc3339_to_ms(value: str) -> int:
    """Alpaca timestamps carry up to nanoseconds and a trailing Z; trim to microseconds for fromisoformat."""
    value = value.replace('Z', '+00:00')
    if '.' in value:
        head, rest = value.split('.', 1)
        sign = '+' if '+' in rest else ('-' if '-' in rest else None)
        if sign:
            digits, tz = rest.split(sign, 1)
            tz = sign + tz
        else:
            digits, tz = rest, ''
        value = f'{head}.{(digits + "000000")[:6]}{tz}'
    return int(datetime.fromisoformat(value).timestamp() * 1000)


def ms_to_rfc3339(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def auth_headers(api_key: str, api_secret: str) -> dict:
    return {
        'APCA-API-KEY-ID': api_key,
        'APCA-API-SECRET-KEY': api_secret,
        'Accept': 'application/json',
    }


def resolve_credentials() -> tuple[str, str]:
    """
    The data API needs a key even for candles. Inside a live session the keys of the selected
    exchange API key row are used; outside one (developer scripts) the ALPACA_API_KEY /
    ALPACA_API_SECRET environment variables are the fallback. Anything else is a clear error
    instead of an anonymous 401 from Alpaca.
    """
    from jesse.store import store

    api_key_row = getattr(store.app, 'exchange_api_key', None)
    if api_key_row is not None and getattr(api_key_row, 'api_key', None):
        return api_key_row.api_key, api_key_row.api_secret

    api_key = os.environ.get('ALPACA_API_KEY')
    api_secret = os.environ.get('ALPACA_API_SECRET')
    if api_key and api_secret:
        return api_key, api_secret

    # Paper-trading sessions (Jesse's own simulation) select no key, but Alpaca's data API still
    # needs one: borrow the oldest saved Alpaca key for market data only.
    try:
        from jesse.models.ExchangeApiKeys import ExchangeApiKeys
        from jesse.services.db import database
        if database.is_closed():
            database.open_connection()
        row = (
            ExchangeApiKeys.select()
            .where(ExchangeApiKeys.exchange_name.startswith('Alpaca'))
            .order_by(ExchangeApiKeys.created_at)
            .first()
        )
        if row is not None:
            return row.api_key, row.api_secret
    except Exception:
        pass

    raise exceptions.InvalidExchangeApiKeys(
        'Alpaca market data requires an API key. Save an Alpaca exchange API key in the dashboard '
        '(paper keys work for data), or export ALPACA_API_KEY and ALPACA_API_SECRET for development scripts.'
    )


def detect_feed(session: requests.Session, headers: dict) -> str:
    """
    Decide between SIP and IEX once per process. Requesting SIP bars from the last few minutes is
    the cheapest test: Basic accounts get 403 for that window, subscribed accounts get 200.
    Any other failure falls back to IEX, which every account can use.
    """
    start = ms_to_rfc3339(jh.now() - 5 * 60_000)
    try:
        response = session.get(
            DATA_ENDPOINT + '/v2/stocks/bars',
            params={'symbols': 'SPY', 'timeframe': '1Min', 'start': start, 'limit': 1, 'feed': FEED_SIP},
            headers=headers,
            timeout=15,
        )
    except requests.exceptions.RequestException:
        return FEED_IEX
    if response.status_code == 200:
        return FEED_SIP
    if response.status_code == _SIP_RECENCY_RESTRICTED_STATUS:
        return FEED_IEX
    return FEED_IEX


def is_tradable_equity(asset: dict) -> bool:
    """Alpaca lists OTC names and untradable shells in the same catalog; Jesse only exposes listed, tradable stocks."""
    return (
        asset.get('class') == 'us_equity'
        and asset.get('status') == 'active'
        and bool(asset.get('tradable'))
        and asset.get('exchange') != 'OTC'
    )
