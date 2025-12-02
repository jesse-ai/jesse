import jesse.helpers as jh
import jesse.services.logger as logger
from jesse.config import config
from jesse.services.notifier import notify
from jesse.enums import order_statuses
from jesse.models.Order import Order
from jesse.store import store
from jesse.repositories import order_repository
from jesse.enums import order_types
from jesse.services import closed_trade_service


def create_order(attributes: dict, should_silent: bool = False) -> Order:
    if attributes.get('created_at') is None:
        attributes['created_at'] = jh.now_to_timestamp()
    
    order = Order(attributes)
    
    # if for example we are in a live trade mode:
    if not should_silent:
        if jh.is_live():
            _notify_submission(order)
        
        if jh.is_debuggable('order_submission') and (order.is_active or order.is_queued):
            txt: str = f'{"QUEUED" if order.is_queued else "SUBMITTED"} order: {order.symbol}, {order.type}, {order.side}, {order.qty}'
            if order.price:
                txt += f', ${jh.format_price(order.price)}'
            logger.info(txt)
    
    e = store.exchanges.get_exchange(order.exchange)
    e.on_order_submission(order)


    store.orders.add_order(order)

    # if it's paper trading or backtesting (basicly not live trading), we add the order to the to_execute list to later simulate the execution.
    if not jh.is_livetrading() and order.type == order_types.MARKET:
        store.orders.to_execute.append(order)
    
    # if it's live/paper trading, we store the order in the database.
    if jh.is_live():
        order_repository.store_or_update(order)
    
    return order


def execute_order(order: Order, silent: bool = False) -> None:
    if order.is_canceled or order.is_executed:
        return
    
    order.executed_at = jh.now_to_timestamp()
    order.status = order_statuses.EXECUTED

    # if it's not live trading, we set the filled qty to the qty. 
    if not jh.is_livetrading():
        order.filled_qty = order.qty

    if not silent:
        txt = f'EXECUTED order: {order.symbol}, {order.type}, {order.side}, {order.qty}'
        if order.price:
            txt += f', ${jh.format_price(order.price)}'
        
        if jh.is_debuggable('order_execution'):
            logger.info(txt)
        
        if jh.is_live():
            if config['env']['notifications']['events']['executed_orders']:
                notify(txt)
    
    closed_trade_service.add_executed_order(order)
    
    e = store.exchanges.get_exchange(order.exchange)
    e.on_order_execution(order)
    
    p = store.positions.get_position(order.exchange, order.symbol)
    if p:
        p._on_executed_order(order)


def execute_order_partially(order: Order, silent: bool = False) -> None:
    order.executed_at = jh.now_to_timestamp()
    order.status = order_statuses.PARTIALLY_FILLED
    
    if not silent:
        txt = f"PARTIALLY FILLED: {order.symbol}, {order.type}, {order.side}, filled qty: {order.filled_qty}, remaining qty: {order.remaining_qty}, price: {jh.format_price(order.price)}"
        
        if jh.is_debuggable('order_execution'):
            logger.info(txt)
        
        if jh.is_live():
            if config['env']['notifications']['events']['executed_orders']:
                notify(txt)
    
    closed_trade_service.add_executed_order(order)
    
    p = store.positions.get_position(order.exchange, order.symbol)
    
    if p:
        p._on_executed_order(order)


def execute_simulated_market_orders() -> None:
    if not store.orders.to_execute:
        return

    for o in store.orders.to_execute:
        execute_order(o)

    store.orders.to_execute = []


def cancel_order(order: Order, silent: bool = False, source: str = '') -> None:
    if order.is_canceled or order.is_executed:
        return
    
    if source == 'stream' and order.is_queued:
        return
    
    order.canceled_at = jh.now_to_timestamp()
    order.status = order_statuses.CANCELED
    
    if not silent:
        txt = f'CANCELED order: {order.symbol}, {order.type}, {order.side}, {order.qty}'
        if order.price:
            txt += f', ${jh.format_price(order.price)}'
        if jh.is_debuggable('order_cancellation'):
            logger.info(txt)
        if jh.is_live():
            if config['env']['notifications']['events']['cancelled_orders']:
                notify(txt)
    
    e = store.exchanges.get_exchange(order.exchange)
    e.on_order_cancellation(order)


def queue_order(order: Order) -> None:
    order.status = order_statuses.QUEUED
    order.canceled_at = None
    if jh.is_debuggable('order_submission'):
        txt = f'QUEUED order: {order.symbol}, {order.type}, {order.side}, {order.qty}'
        if order.price:
            txt += f', ${jh.format_price(order.price)}'
            logger.info(txt)
    _notify_submission(order)


def resubmit_order(order: Order) -> None:
    if not order.is_queued:
        raise Exception(f'Cannot resubmit an order that is not queued. Current status: {order.status}')
    
    order.id = jh.generate_unique_id()
    order.status = order_statuses.ACTIVE
    order.canceled_at = None
    if jh.is_debuggable('order_submission'):
        txt: str = f'SUBMITTED order: {order.symbol}, {order.type}, {order.side}, {order.qty}'
        if order.price:
            txt += f', ${jh.format_price(order.price)}'
            logger.info(txt)
    _notify_submission(order)


def _notify_submission(order: Order) -> None:
    if config['env']['notifications']['events']['submitted_orders'] and (order.is_active or order.is_queued):
        txt = f'{"QUEUED" if order.is_queued else "SUBMITTED"} order: {order.symbol}, {order.type}, {order.side}, {order.qty}'
        if order.price:
            txt += f', ${jh.format_price(order.price)}'
        notify(txt)


def initialize_orders_state() -> None:
    for exchange in config['app']['trading_exchanges']:
        for symbol in config['app']['trading_symbols']:
            key = f'{exchange}-{symbol}'
            store.orders.storage[key] = []
            store.orders.active_storage[key] = []