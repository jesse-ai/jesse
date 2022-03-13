class sides:
    BUY = 'buy'
    SELL = 'sell'


class trade_types:
    LONG = 'long'
    SHORT = 'short'


class order_statuses:
    ACTIVE = 'ACTIVE'
    CANCELED = 'CANCELED'
    EXECUTED = 'EXECUTED'
    PARTIALLY_FILLED = 'PARTIALLY FILLED'
    QUEUED = 'QUEUED'
    LIQUIDATED = 'LIQUIDATED'


class timeframes:
    MINUTE_1 = '1m'
    MINUTE_3 = '3m'
    MINUTE_5 = '5m'
    MINUTE_15 = '15m'
    MINUTE_30 = '30m'
    MINUTE_45 = '45m'
    HOUR_1 = '1h'
    HOUR_2 = '2h'
    HOUR_3 = '3h'
    HOUR_4 = '4h'
    HOUR_6 = '6h'
    HOUR_8 = '8h'
    HOUR_12 = '12h'
    DAY_1 = '1D'


class colors:
    GREEN = 'green'
    YELLOW = 'yellow'
    RED = 'red'
    MAGENTA = 'magenta'
    BLACK = 'black'


class order_types:
    MARKET = 'MARKET'
    LIMIT = 'LIMIT'
    STOP = 'STOP'
    FOK = 'FOK'
    STOP_LIMIT = 'STOP LIMIT'


class exchanges:
    SANDBOX = 'Sandbox'
    COINBASE = 'Coinbase'
    BITFINEX = 'Bitfinex'
    BINANCE = 'Binance'
    BINANCE_FUTURES = 'Binance Futures'
    TESTNET_BINANCE_FUTURES = 'Testnet Binance Futures'
    BYBIT_PERPETUAL = 'Bybit Perpetual'
    TESTNET_BYBIT_PERPETUAL = 'Testnet Bybit Perpetual'
    FTX_FUTURES = 'FTX Futures'


class migration_actions:
    ADD = 'add'
    DROP = 'drop'
    RENAME = 'rename'
    MODIFY_TYPE = 'modify_type'
    ALLOW_NULL = 'allow_null'
    DENY_NULL = 'deny_null'


class order_submitted_via:
    STOP_LOSS = 'stop-loss'
    TAKE_PROFIT = 'take-profit'
