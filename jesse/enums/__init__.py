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
    QUEUED = 'QUEUED'


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
    DAY_3 = '3D'
    WEEK_1 = '1W'


class colors:
    GREEN = 'green'
    YELLOW = 'yellow'
    RED = 'red'
    MAGENTA = 'magenta'
    BLACK = 'black'


class order_roles:
    OPEN_POSITION = 'OPEN POSITION'
    CLOSE_POSITION = 'CLOSE POSITION'
    INCREASE_POSITION = 'INCREASE POSITION'
    REDUCE_POSITION = 'REDUCE POSITION'


class order_flags:
    OCO = 'OCO'
    POST_ONLY = 'PostOnly'
    CLOSE = 'Close'
    HIDDEN = 'Hidden'
    REDUCE_ONLY = 'ReduceOnly'


class order_types:
    MARKET = 'MARKET'
    LIMIT = 'LIMIT'
    STOP = 'STOP'
    FOK = 'FOK'
    STOP_LIMIT = 'STOP LIMIT'


class exchanges:
    COINBASE = 'Coinbase'
    BITFINEX = 'Bitfinex'
    BINANCE = 'Binance'
    BINANCE_FUTURES = 'Binance Futures'
    TESTNET_BINANCE_FUTURES = 'Testnet Binance Futures'
    SANDBOX = 'Sandbox'
