from .state_app import AppState
from .state_candles import CandlesState
from .state_closed_trades import ClosedTrades
from .state_exchanges import ExchangesState
from .state_logs import LogsState
from .state_orderbook import OrderbookState
from .state_orders import OrdersState
from .state_positions import PositionsState
from .state_reinforcement_learning import ReinforcementLearningState
from .state_tickers import TickersState
from .state_trades import TradesState


class StoreClass:
    app = AppState()
    orders = OrdersState() # requires initialization
    closed_trades = ClosedTrades()
    logs = LogsState()
    exchanges = ExchangesState() # requires initialization
    candles = CandlesState()
    positions = PositionsState() # requires initialization
    reinforcement_learning = ReinforcementLearningState()
    tickers = TickersState()
    trades = TradesState()
    orderbooks = OrderbookState()
    
    @property
    def rl(self):
        """Alias for reinforcement_learning"""
        return self.reinforcement_learning

    def __init__(self) -> None:
        # used in self.shared_vars property of Strategy class
        self.vars = {}

    def reset(self) -> None:
        self.app = AppState()
        self.orders = OrdersState()
        self.closed_trades = ClosedTrades()
        self.logs = LogsState()
        self.exchanges = ExchangesState()
        self.candles = CandlesState()
        self.positions = PositionsState()
        self.reinforcement_learning = ReinforcementLearningState()
        self.tickers = TickersState()
        self.trades = TradesState()
        self.orderbooks = OrderbookState()


store = StoreClass()
