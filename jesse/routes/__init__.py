import sys
from typing import List, Any

import jesse.helpers as jh
from jesse import exceptions
from jesse.models import Route


class RouterClass:
    def __init__(self) -> None:
        self.routes = []
        self.data_candles = [] # used in legacy code (probably will be replaced in the future with self.data_routes)
        self.data_routes = [] # same as data_candles but instead of dict, it's a Route object

    def _reset(self) -> None:
        self.routes = []
        self.data_candles = []
        self.data_routes = []

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
            'exchange': r['exchange'],
            'symbol': r['symbol'],
            'timeframe': r['timeframe']
        } for r in self.data_candles]

    @property
    def all_formatted_routes(self) -> list:
        return self.formatted_routes + self.formatted_data_routes

    def initiate(self, routes: list, data_routes: list = None):
        if data_routes is None:
            data_routes = []
        self.set_routes(routes)
        self.set_data_candles(data_routes)
        from jesse.store import store
        store.reset(force_install_routes=jh.is_unit_testing())

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

    def set_data_routes(self, routes: List[Any]) -> None:
        self.data_routes = []
        for r in routes:
            self.data_routes.append(Route(r["exchange"], r["symbol"], r["timeframe"], None, None))

    def set_data_candles(self, data_candles: list) -> None:
        self.data_candles = data_candles
        self.set_data_routes(data_candles)


router: RouterClass = RouterClass()
