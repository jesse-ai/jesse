import sys
from typing import Dict, List, Any
from jesse.config import config
import jesse.helpers as jh
from jesse import exceptions
from jesse.models.Route import Route
from jesse import exceptions

class RouterClass:
    def __init__(self) -> None:
        self.routes: List[Route] = []
        self.data_routes: List[Route] = []

    def _reset(self) -> None:
        self.routes = []
        self.data_routes = []

    def initiate(self, routes: list, data_routes: list = None):
        if data_routes is None:
            data_routes = []

        self.set_routes(routes)
        self.set_data_routes(data_routes)

        considering_candles = set()

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
                raise exceptions.InvalidRoutes(
                    'each exchange-symbol pair can be traded only once. \nMore info: https://docs.jesse.trade/docs/routes.html#trading-multiple-routes')

        # check to make sure if trading more than one route, they all have the same quote
        # currency because otherwise we cannot calculate the correct performance metrics
        first_routes_quote = jh.quote_asset(router.routes[0].symbol)
        for r in router.routes:
            if jh.quote_asset(r.symbol) != first_routes_quote:
                raise exceptions.InvalidRoutes('All trading routes must have the same quote asset.')

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

        for e in router.data_routes:
            considering_candles.add((e.exchange, e.symbol))
            considering_exchanges.add(e.exchange)
            considering_symbols.add(e.symbol)
            considering_timeframes.add(e.timeframe)

        # 1m must be present at all times
        considering_timeframes.add('1m')

        config['app']['considering_candles'] = tuple(considering_candles)
        config['app']['considering_exchanges'] = tuple(considering_exchanges)

        config['app']['considering_symbols'] = tuple(considering_symbols)
        config['app']['considering_timeframes'] = tuple(considering_timeframes)
        config['app']['trading_exchanges'] = tuple(trading_exchanges)
        config['app']['trading_symbols'] = tuple(trading_symbols)
        config['app']['trading_timeframes'] = tuple(trading_timeframes)

    def set_routes(self, routes: List[Any]) -> None:
        self._reset()

        self.routes = []

        for r in routes:
            # validate strategy that the strategy file exists (if sent as a string)
            if isinstance(r["strategy"], str):
                strategy_name = r["strategy"]
                if jh.is_unit_testing():
                    path = sys.path[0]
                    # live plugin
                    if path.endswith('jesse-live'):
                        strategies_dir = f'{sys.path[0]}/tests/strategies'
                    # main framework
                    else:
                        strategies_dir = f'{sys.path[0]}/jesse/strategies'
                    exists = jh.file_exists(f"{strategies_dir}/{strategy_name}/__init__.py")
                else:
                    exists = jh.file_exists(f'strategies/{strategy_name}/__init__.py')
            else:
                exists = True

            if not exists and isinstance(r["strategy"], str):
                raise exceptions.InvalidRoutes(
                    f'A strategy with the name of "{r["strategy"]}" could not be found.')

            self.routes.append(Route(r["exchange"], r["symbol"], r["timeframe"], r["strategy"], None))

    def set_data_routes(self, routes: List[Dict[str, str]]) -> None:
        self.data_routes: List[Route] = []
        for r in routes:
            self.data_routes.append(Route(r['exchange'], r['symbol'], r['timeframe'], None, None))

    @property
    def formatted_routes(self) -> list:
        """
        Example:
        [{'exchange': 'Binance', 'strategy': 'A1', 'symbol': 'BTC-USDT', 'timeframe': '1m'}]
        """
        return [
            {
                'exchange': r.exchange,
                'symbol': r.symbol,
                'timeframe': r.timeframe,
                'strategy': r.strategy_name,
            }
            for r in self.routes
        ]

    @property
    def formatted_data_routes(self) -> list:
        """
        Example:
        [{'exchange': 'Binance', 'symbol': 'BTC-USD', 'timeframe': '3m'}]
        """
        return [{
            'exchange': r.exchange,
            'symbol': r.symbol,
            'timeframe': r.timeframe
        } for r in self.data_routes]

    @property
    def all_formatted_routes(self) -> list:
        return self.formatted_routes + self.formatted_data_routes

    @property
    def trading_routes_count(self) -> int:
        return len(self.routes)
    
    @property
    def data_routes_count(self) -> int:
        return len(self.data_routes)
    
    @property
    def all_routes_count(self) -> int:
        return self.trading_routes_count + self.data_routes_count
    
router: RouterClass = RouterClass()
