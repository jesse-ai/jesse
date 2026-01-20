from jesse.config import config
from jesse.models import Position
from jesse.store import store
import jesse.helpers as jh
from jesse.exceptions import EmptyPosition, OpenPositionError
from jesse.services import closed_trade_service
from jesse.enums import trade_types
from jesse.utils import sum_floats, subtract_floats
from jesse.enums import order_types
from jesse.models import Order
from jesse.services import logger


def initialize_positions_state() -> None:
    for exchange in config['app']['trading_exchanges']:
        for symbol in config['app']['trading_symbols']:
            key: str = f'{exchange}-{symbol}'
            store.positions.storage[key] = create_position(exchange, symbol)


def create_position(exchange_name: str, symbol: str, attributes: dict = None) -> Position:
    p = Position(attributes)
    if p.id is None:
        p.id = jh.generate_unique_id()  
    p.exchange_name = exchange_name
    p.exchange = store.exchanges.get_exchange(exchange_name)
    p.symbol = symbol
    return p


def _mutating_close(position: Position, close_price: float) -> None:
    if position.is_close and position._can_mutate_qty:
        raise EmptyPosition('The position is already closed.')

    position.exit_price = close_price
    position.closed_at = jh.now_to_timestamp()

    if position.exchange and position.exchange.type == 'futures':
        # just to prevent confusion
        close_qty = abs(position.qty)
        estimated_profit = jh.estimate_PNL(
            close_qty, position.entry_price,
            close_price, position.type
        )
        position.exchange.add_realized_pnl(estimated_profit)
        position.exchange.temp_reduced_amount[jh.base_asset(position.symbol)] += abs(close_qty * close_price)

    if position._can_mutate_qty:
        _update_qty(position, 0, operation='set')

    # reset entry_price
    position.entry_price = None

    _close(position)


def _close(position: Position):
    closed_trade_service.close_trade(position)


def _mutating_reduce(position: Position, qty: float, price: float) -> None:
    if not position._can_mutate_qty:
        return

    if position.is_open is False:
        raise EmptyPosition('The position is closed.')

    # just to prevent confusion
    qty = abs(qty)

    estimated_profit = jh.estimate_PNL(qty, position.entry_price, price, position.type)

    if position.exchange and position.exchange.type == 'futures':
        # position.exchange.increase_futures_balance(qty * position.entry_price + estimated_profit)
        position.exchange.add_realized_pnl(estimated_profit)
        position.exchange.temp_reduced_amount[jh.base_asset(position.symbol)] += abs(qty * price)

    if position.type == trade_types.LONG:
        _update_qty(position, qty, operation='subtract')
    elif position.type == trade_types.SHORT:
        _update_qty(position, qty, operation='add')


def _mutating_increase(position: Position, qty: float, price: float) -> None:
    if not position.is_open:
        raise OpenPositionError('position must be already open in order to increase its size')

    qty = abs(qty)

    position.entry_price = jh.estimate_average_price(
        qty, price, position.qty,
        position.entry_price
    )

    if position._can_mutate_qty:
        if position.type == trade_types.LONG:
            _update_qty(position, qty, operation='add')
        elif position.type == trade_types.SHORT:
            _update_qty(position, qty, operation='subtract')


def _mutating_open(position: Position, qty: float, price: float) -> None:
    if position.is_open and position._can_mutate_qty:
        raise OpenPositionError('an already open position cannot be opened')

    position.entry_price = price
    position.exit_price = None

    if position._can_mutate_qty:
        _update_qty(position, qty, operation='set')

    position.opened_at = jh.now_to_timestamp()

    _open(position)


def _update_qty(position: Position, qty: float, operation='set'):
    position.previous_qty = position.qty

    if position.exchange_type == 'spot':
        if operation == 'set':
            position.qty = qty * (1 - position.exchange.fee_rate)
        elif operation == 'add':
            position.qty = sum_floats(position.qty, qty * (1 - position.exchange.fee_rate))
        elif operation == 'subtract':
            # fees are taken from the quote currency. in spot mode, sell orders cause
            # the qty to reduce but fees are handled on the exchange balance stuff
            position.qty = subtract_floats(position.qty, qty)

    elif position.exchange_type == 'futures':
        if operation == 'set':
            position.qty = qty
        elif operation == 'add':
            position.qty = sum_floats(position.qty, qty)
        elif operation == 'subtract':
            position.qty = subtract_floats(position.qty, qty)
    else:
        raise NotImplementedError('exchange type not implemented')


def _open(position: Position, p_orders: list = None):
    closed_trade_service.open_trade(position, p_orders)


def on_executed_order(position: Position, order: Order) -> None:
    # futures (live)
    if jh.is_livetrading() and position.exchange_type == 'futures':
        # if position got closed because of this order
        if order.is_partially_filled:
            before_qty = position.qty - order.filled_qty
        else:
            before_qty = position.qty - order.qty
        after_qty = position.qty
        if before_qty != 0 and after_qty == 0:
            _close(position)
    # spot (live)
    elif jh.is_livetrading() and position.exchange_type == 'spot':
        # if position got closed because of this order
        before_qty = position.previous_qty
        after_qty = position.qty
        qty = order.qty
        price = order.price
        closing_position = before_qty > position._min_qty > after_qty
        if closing_position:
            _mutating_close(position, price)
        opening_position = before_qty < position._min_qty < after_qty
        if opening_position:
            _mutating_open(position, qty, price)
        increasing_position = after_qty > before_qty > position._min_qty
        if increasing_position:
            _mutating_increase(position, qty, price)
        reducing_position = position._min_qty < after_qty < before_qty
        if reducing_position:
            _mutating_reduce(position, qty, price)
    else:  # backtest (both futures and spot)
        qty = order.qty
        price = order.price

        if position.exchange and position.exchange.type == 'futures':
            position.exchange.charge_fee(qty * price)

        # order opens position
        if position.qty == 0:
            change_balance = order.type == order_types.MARKET
            _mutating_open(position, qty, price)
        # order closes position
        elif (sum_floats(position.qty, qty)) == 0:
            _mutating_close(position, price)
        # order increases the size of the position
        elif position.qty * qty > 0:
            if order.reduce_only:
                logger.info('Did not increase position because order is a reduce_only order')
            else:
                _mutating_increase(position, qty, price)
        # order reduces the size of the position
        elif position.qty * qty < 0:
            # if size of the order is big enough to both close the
            # position AND open it on the opposite side
            if abs(qty) > abs(position.qty):
                if order.reduce_only:
                    logger.info(
                        f'Executed order is bigger than the current position size but it is a reduce_only order so it just closes it. Order QTY: {qty}, Position QTY: {position.qty}')
                    _mutating_close(position, price)
                else:
                    logger.info(
                        f'Executed order is big enough to not close, but flip the position type. Order QTY: {qty}, Position QTY: {position.qty}')
                    diff_qty = sum_floats(position.qty, qty)
                    _mutating_close(position, price)
                    _mutating_open(position, diff_qty, price)
            else:
                _mutating_reduce(position, qty, price)

    if position.strategy:
        position.strategy._on_updated_position(order)


def update_from_stream(position: Position, data: dict, is_initial: bool, open_trade: dict = None, p_orders: list = None) -> None:
    """
    Used for updating the position from the WS stream (only for live trading)
    """
    before_qty = abs(position.qty)
    after_qty = abs(data['qty'])

    if position.exchange_type == 'futures':
        position.entry_price = data['entry_price']
        position._liquidation_price = data['liquidation_price']
    else:  # spot
        if after_qty > position._min_qty and position.entry_price is None:
            position.entry_price = position.current_price

    # if the new qty (data['qty']) is different than the current (self.qty) then update it:
    if position.qty != data['qty']:
        position.previous_qty = position.qty
        position.qty = data['qty']

    opening_position = before_qty <= position._min_qty < after_qty
    closing_position = before_qty > position._min_qty >= after_qty
    if opening_position:
        # if is_initial:
        #     from jesse.store import store
        #     store.closed_trades.add_order_record_only(
        #         self.exchange_name, self.symbol, jh.type_to_side(self.type),
        #         self.qty, self.entry_price
        #     )
        position.opened_at = jh.now_to_timestamp()
        _open(position, p_orders)
    elif closing_position:
        position.closed_at = jh.now_to_timestamp()
