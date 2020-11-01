import jesse.helpers as jh
from jesse.enums import sides, order_flags
from jesse.exceptions import OrderNotAllowed, InvalidStrategy
from jesse.models import Order
from jesse.models import Position


class Broker:
    def __init__(self, position, exchange, symbol, timeframe):
        self.position: Position = position
        self.symbol = symbol
        self.timeframe = timeframe
        self.exchange = exchange
        from jesse.services.api import api
        self.api = api

    @staticmethod
    def _validate_qty(qty):
        if qty == 0:
            raise InvalidStrategy('qty cannot be 0')

    def sell_at_market(self, qty, role=None) -> Order:
        self._validate_qty(qty)

        return self.api.market_order(
            self.exchange,
            self.symbol,
            abs(qty),
            self.position.current_price,
            sides.SELL,
            role, []
        )

    def sell_at(self, qty, price, role=None) -> Order:
        self._validate_qty(qty)

        if price < 0:
            raise ValueError('price cannot be negative.')

        # if price <= self.position.current_price:
        #     raise OrderNotAllowed(
        #         'Cannot LIMIT sell at ${} when current_price is ${}'.format(
        #             price,
        #             self.position.current_price
        #         )
        #     )

        return self.api.limit_order(
            self.exchange,
            self.symbol,
            abs(qty),
            price,
            sides.SELL,
            role,
            []
        )

    def buy_at_market(self, qty, role=None) -> Order:
        self._validate_qty(qty)

        return self.api.market_order(
            self.exchange,
            self.symbol,
            abs(qty),
            self.position.current_price,
            sides.BUY,
            role,
            []
        )

    def buy_at(self, qty, price, role=None) -> Order:
        self._validate_qty(qty)

        if price < 0:
            raise ValueError('price cannot be negative.')

        # if price >= self.position.current_price:
        #     raise OrderNotAllowed(
        #         'Cannot LIMIT buy at ${} when current_price is ${}'.format(
        #             price,
        #             self.position.current_price
        #         )
        #     )

        return self.api.limit_order(
            self.exchange,
            self.symbol,
            abs(qty),
            price,
            sides.BUY,
            role,
            []
        )

    def reduce_position_at(self, qty, price, role=None) -> Order:
        self._validate_qty(qty)

        qty = abs(qty)

        # validation
        if price < 0:
            raise ValueError('price cannot be negative.')

        # validation
        if self.position.is_close:
            raise OrderNotAllowed(
                'Cannot submit a reduce_position order when there is not open position'
            )

        side = jh.opposite_side(jh.type_to_side(self.position.type))

        # validation
        if side == 'buy' and price >= self.position.current_price:
            raise OrderNotAllowed(
                'Cannot reduce (via LIMIT) buy at ${} when current_price is ${}'.format(
                    price,
                    self.position.current_price
                )
            )
        # validation
        if side == 'sell' and price <= self.position.current_price:
            raise OrderNotAllowed(
                'Cannot reduce (via LIMIT) sell at ${} when current_price is ${}'.format(
                    price,
                    self.position.current_price
                )
            )

        return self.api.limit_order(
            self.exchange,
            self.symbol,
            qty,
            price,
            side,
            role,
            [order_flags.REDUCE_ONLY]
        )

    def start_profit_at(self, side, qty, price, role=None) -> Order:
        self._validate_qty(qty)

        if price < 0:
            raise ValueError('price cannot be negative.')

        if side == 'buy' and price < self.position.current_price:
            raise OrderNotAllowed(
                'A buy start_profit({}) order must have a price higher than current_price({}).'.format(
                    price,
                    self.position.current_price
                )
            )
        if side == 'sell' and price > self.position.current_price:
            raise OrderNotAllowed(
                'A sell start_profit({}) order must have a price lower than current_price({}).'.format(
                    price,
                    self.position.current_price
                )
            )

        return self.api.stop_order(
            self.exchange,
            self.symbol,
            abs(qty),
            price,
            side,
            role,
            []
        )

    def stop_loss_at(self, qty, price, role=None) -> Order:
        self._validate_qty(qty)

        # validation
        if self.position.is_close:
            raise OrderNotAllowed(
                'Cannot submit a (reduce_only) stop_loss order when there is not open position'
            )

        side = jh.opposite_side(jh.type_to_side(self.position.type))

        if price < 0:
            raise ValueError('price cannot be negative.')

        if side == 'buy' and price < self.position.current_price:
            raise OrderNotAllowed(
                'Cannot submit a buy stop at {} when current price is {}'.format(
                    price,
                    self.position.current_price
                )
            )
        if side == 'sell' and price > self.position.current_price:
            raise OrderNotAllowed(
                'Cannot submit a sell stop at {} when current price is {}.'.format(
                    price,
                    self.position.current_price
                )
            )

        return self.api.stop_order(
            self.exchange,
            self.symbol,
            abs(qty),
            price,
            side,
            role,
            [order_flags.REDUCE_ONLY]
        )

    def cancel_all_orders(self):
        return self.api.cancel_all_orders(self.exchange, self.symbol)

    def cancel_order(self, order_id: str):
        return self.api.cancel_order(self.exchange, self.symbol, order_id)
