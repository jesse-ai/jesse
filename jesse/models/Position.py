from typing import Union
import numpy as np
import jesse.helpers as jh


class Position:
    id: str = None
    entry_price: float = None
    exit_price: float = None
    current_price: float = None
    qty: float = 0
    previous_qty: float = 0
    opened_at: int = None
    closed_at: int = None
    _mark_price: float = None
    _funding_rate: float = None
    _next_funding_timestamp: int = None
    _liquidation_price: float = None
    exchange_name: str = None
    exchange = None
    symbol: str = None
    strategy = None
    
    def __init__(self, attributes: dict = None) -> None:
        if attributes is None:
            attributes = {}

        for a in attributes:
            setattr(self, a, attributes[a])

    @property
    def mark_price(self) -> float:
        if not jh.is_live():
            return self.current_price

        if self.exchange_type == 'spot':
            return self.current_price

        return self._mark_price

    @property
    def funding_rate(self) -> float:
        if not jh.is_live():
            return 0

        if self.exchange_type == 'spot':
            raise ValueError('funding rate is not applicable to spot trading')

        return self._funding_rate

    @property
    def next_funding_timestamp(self) -> Union[int, None]:
        if not jh.is_live():
            return None

        if self.exchange_type == 'spot':
            raise ValueError('funding rate is not applicable to spot trading')

        return self._next_funding_timestamp

    @property
    def value(self) -> float:
        """
        The value of open position in the quote currency

        :return: float
        """
        if self.is_close:
            return 0

        if self.current_price is None:
            return None

        return abs(self.current_price * self.qty)

    @property
    def type(self) -> str:
        """
        The type of open position - long, short, or close

        :return: str
        """
        if self.is_long:
            return 'long'
        elif self.is_short:
            return 'short'

        return 'close'

    @property
    def pnl_percentage(self) -> float:
        """
        Alias for self.roi

        :return: float
        """
        return self.roi

    @property
    def roi(self) -> float:
        """
        Return on Investment in percentage
        More at: https://www.binance.com/en/support/faq/5b9ad93cb4854f5990b9fb97c03cfbeb
        """
        if self.pnl == 0:
            return 0

        return self.pnl / self.total_cost * 100

    @property
    def total_cost(self) -> float:
        """
        How much we paid to open this position (currently does not include fees, should we?!)
        """
        if self.is_close:
            return np.nan

        base_cost = self.entry_price * abs(self.qty)
        if self.strategy:
            return base_cost / self.leverage

        return base_cost

    @property
    def leverage(self) -> Union[int, np.float64]:
        if self.exchange_type == 'spot':
            return 1

        if self.strategy:
            return self.strategy.leverage
        else:
            return np.nan

    @property
    def exchange_type(self) -> str:
        return self.exchange.type

    @property
    def entry_margin(self) -> float:
        """
        Alias for self.total_cost
        """
        return self.total_cost

    @property
    def pnl(self) -> float:
        """
        The PNL of the position

        :return: float
        """
        if abs(self.qty) < self._min_qty:
            return 0

        if self.entry_price is None:
            return 0

        if self.value is None:
            return 0

        diff = self.value - abs(self.entry_price * self.qty)

        return -diff if self.type == 'short' else diff

    @property
    def is_open(self) -> bool:
        """
        Is the current position open?

        :return: bool
        """
        return self.type in ['long', 'short']

    @property
    def is_close(self) -> bool:
        """
        Is the current position close?

        :return: bool
        """
        return self.type == 'close'

    @property
    def is_long(self) -> bool:
        """
        Is the current position a long position?

        :return: bool
        """
        return self.qty > self._min_qty

    @property
    def is_short(self) -> bool:
        """
        Is the current position a short position?

        :return: bool
        """
        return self.qty < -abs(self._min_qty)

    @property
    def mode(self) -> str:
        if self.exchange.type == 'spot':
            return 'spot'
        else:
            return self.exchange.futures_leverage_mode

    @property
    def liquidation_price(self) -> Union[float, np.float64]:
        """
        The price at which the position gets liquidated. formulas are taken from:
        https://help.bybit.com/hc/en-us/articles/900000181046-Liquidation-Price-USDT-Contract-
        """
        if self.is_close:
            return np.nan

        if jh.is_livetrading():
            return self._liquidation_price

        if self.mode in ['cross', 'spot']:
            return np.nan

        elif self.mode == 'isolated':
            if self.type == 'long':
                return self.entry_price * (1 - self._initial_margin_rate + 0.004)
            elif self.type == 'short':
                return self.entry_price * (1 + self._initial_margin_rate - 0.004)
            else:
                return np.nan

        else:
            raise ValueError

    @property
    def _initial_margin_rate(self) -> float:
        return 1 / self.leverage

    @property
    def bankruptcy_price(self) -> Union[float, np.float64]:
        if self.type == 'long':
            return self.entry_price * (1 - self._initial_margin_rate)
        elif self.type == 'short':
            return self.entry_price * (1 + self._initial_margin_rate)
        else:
            return np.nan

    @property
    def to_dict(self):
        return {
            'entry_price': self.entry_price,
            'qty': self.qty,
            'current_price': self.current_price,
            'value': self.value,
            'type': self.type,
            'exchange': self.exchange_name,
            'pnl': self.pnl,
            'pnl_percentage': self.pnl_percentage,
            'leverage': self.leverage,
            'liquidation_price': self.liquidation_price,
            'bankruptcy_price': self.bankruptcy_price,
            'mode': self.mode,
        }

    @property
    def _min_notional_size(self) -> float:
        if not (jh.is_livetrading() and self.exchange_type == 'spot'):
            return 0

        return self.exchange.vars['precisions'][self.symbol]['min_notional_size']

    @property
    def _min_qty(self) -> float:
        if not (jh.is_livetrading() and self.exchange_type == 'spot'):
            return 0

        # first check exchange return min_qty or not
        if 'min_qty' in self.exchange.vars['precisions'][self.symbol]:
            return self.exchange.vars['precisions'][self.symbol]['min_qty']

        if self._min_notional_size and self.current_price:
            return self._min_notional_size / self.current_price
        else:
            return 0

    @property
    def _can_mutate_qty(self):
        return not (self.exchange_type == 'spot' and jh.is_livetrading())
