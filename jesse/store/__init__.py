import jesse.helpers as jh
from jesse.config import config
from jesse.exceptions import InvalidRoutes
from jesse.routes import router
from .state_app import AppState
from .state_candles import CandlesState
from .state_completed_trades import ClosedTrades
from .state_exchanges import ExchangesState
from .state_logs import LogsState
from .state_orderbook import OrderbookState
from .state_orders import OrdersState
from .state_positions import PositionsState
from .state_tickers import TickersState
from .state_trades import TradesState


def install_routes() -> None:
    considering_candles = set()

    # when importing market data, considering_candles is all we need
    if jh.is_collecting_data():
        for r in router.market_data:
            considering_candles.add((r.exchange, r.symbol))

        config['app']['considering_candles'] = tuple(considering_candles)
        return

    # validate routes for duplicates:
    # each exchange-symbol pair can be traded only once.
    for r in router.routes:
        considering_candles.add((r.exchange, r.symbol))

        exchange = r.exchange
        symbol = r.symbol
        count = sum(
            ro.exchange == exchange and ro.symbol == symbol
            for ro in router.routes
        )

        if count != 1:
            raise InvalidRoutes(
                'each exchange-symbol pair can be traded only once. \nMore info: https://docs.jesse.trade/docs/routes.html#trading-multiple-routes')

    # check to make sure if trading more than one route, they all have the same quote
    # currency because otherwise we cannot calculate the correct performance metrics
    first_routes_quote = jh.quote_asset(router.routes[0].symbol)
    for r in router.routes:
        if jh.quote_asset(r.symbol) != first_routes_quote:
            raise InvalidRoutes('All trading routes must have the same quote asset.')

    trading_exchanges = set()
    trading_timeframes = set()
    trading_symbols = set()

    for r in router.routes:
        trading_exchanges.add(r.exchange)
        trading_timeframes.add(r.timeframe)
        trading_symbols.add(r.symbol)

    considering_exchanges = trading_exchanges.copy()
    considering_timeframes = trading_timeframes.copy()
    considering_symbols = trading_symbols.copy()

    for e in router.data_candles:
        considering_candles.add((e['exchange'], e['symbol']))
        considering_exchanges.add(e['exchange'])
        considering_symbols.add(e['symbol'])
        considering_timeframes.add(e['timeframe'])

    # 1m must be present at all times
    considering_timeframes.add('1m')

    config['app']['considering_candles'] = tuple(considering_candles)
    config['app']['considering_exchanges'] = tuple(considering_exchanges)

    config['app']['considering_symbols'] = tuple(considering_symbols)
    config['app']['considering_timeframes'] = tuple(considering_timeframes)
    config['app']['trading_exchanges'] = tuple(trading_exchanges)
    config['app']['trading_symbols'] = tuple(trading_symbols)
    config['app']['trading_timeframes'] = tuple(trading_timeframes)


class StoreClass:
    app = AppState()
    orders = OrdersState()
    completed_trades = ClosedTrades()
    logs = LogsState()
    exchanges = ExchangesState()
    candles = CandlesState()
    positions = PositionsState()
    tickers = TickersState()
    trades = TradesState()
    orderbooks = OrderbookState()

    def __init__(self) -> None:
        self.vars = {}

    def reset(self, force_install_routes: bool = False) -> None:
        """
        Resets all the states within the store
        
        Keyword Arguments:
            force_install_routes {bool} -- used for unit_testing (default: {False})
        """
        if not jh.is_unit_testing() or force_install_routes:
            install_routes()

        self.app = AppState()
        self.orders = OrdersState()
        self.completed_trades = ClosedTrades()
        self.logs = LogsState()
        self.exchanges = ExchangesState()
        self.candles = CandlesState()
        self.positions = PositionsState()
        self.tickers = TickersState()
        self.trades = TradesState()
        self.orderbooks = OrderbookState()


store = StoreClass()
