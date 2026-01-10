import jesse.helpers as jh
from jesse.services import logger
from jesse.repositories import closed_trade_repository, order_repository
from jesse.store import store
from jesse.enums import sides
import numpy as np
from jesse.models import ClosedTrade, Order, Position


def create_trade_from_dict(attributes: dict) -> ClosedTrade:
    if attributes.get('created_at') is None:
        attributes['created_at'] = jh.now_to_timestamp()
    
    trade = ClosedTrade(attributes)
    
    # if it's live/paper trading, we store the trade in the database.
    if jh.is_live():
        closed_trade_repository.store_or_update(trade)
    
    return trade


def add_executed_order(executed_order: Order) -> None:
    t = store.closed_trades._get_current_trade(executed_order.exchange, executed_order.symbol)
    
    # if the order is not partially filled, we add it to the trade orders.
    if not executed_order.is_partially_filled:
        executed_order.trade_id = t.id
        t.orders.append(executed_order)

    add_order_record_only(executed_order)

    if jh.is_live():
        order_repository.store_or_update(executed_order)


def add_order_record_only(order: Order) -> None:
    """
    used in add_executed_order() and for when initially adding open positions in live mode.
    used for correct trade-metrics calculations in persistency support for live mode.
    """
    t = store.closed_trades._get_current_trade(order.exchange, order.symbol)
    if order.side == sides.BUY:
        t.buy_orders.append(np.array([abs(order.filled_qty), order.price]))
    elif order.side == sides.SELL:
        t.sell_orders.append(np.array([abs(order.filled_qty), order.price]))
    else:
        raise Exception(f"Invalid order side: {order.side}")


def open_trade(position, p_orders: list = None) -> None:
    t = store.closed_trades._get_current_trade(position.exchange_name, position.symbol)
    t.opened_at = position.opened_at
    t.leverage = position.leverage
    try:
        t.timeframe = position.strategy.timeframe
        t.strategy_name = position.strategy.name
    except AttributeError:
        if not jh.is_unit_testing():
            raise
        # if some unit tests, we don't need to set the timeframe and strategy name.
        t.timeframe = None
        t.strategy_name = None
    t.exchange = position.exchange_name
    t.symbol = position.symbol
    t.type = position.type
    t.session_id = store.app.session_id
    if jh.is_live() or jh.is_paper_trading():
        closed_trade_repository.store_or_update(t)
    if p_orders:
        for order in p_orders:
            order.trade_id = t.id
            order_repository.store_or_update(order)
            add_order_record_only(order)


def close_trade(position: Position) -> None:
    t: ClosedTrade = store.closed_trades._get_current_trade(position.exchange_name, position.symbol)

    if not t.is_open:
        logger.info(
            "Unable to close a trade that is not yet open. If you're getting this in the live mode, it is likely due"
            " to an unstable connection to the exchange, either on your side or the exchange's side. Please submit a"
            " report using the report button so that Jesse's support team can investigate the issue."
        )
        return

    t.closed_at = position.closed_at
    try:
        position.strategy.trades_count += 1
    except AttributeError:
        if not jh.is_unit_testing():
            raise

    if jh.is_livetrading():
        closed_trade_repository.store_or_update(t)

    store.closed_trades.trades.append(t)
    closed_trade_repository.close_trade(t)
    if not jh.is_unit_testing():
        logger.info(
            f"CLOSED a {t.type} trade for {t.exchange}-{t.symbol}: qty: {t.qty},"
            f" entry_price: {t.entry_price}, exit_price: {t.exit_price}, "
            f"PNL: {round(t.pnl, 2)} ({round(t.pnl_percentage, 2)}%)"
        )
    store.closed_trades._reset_current_trade(position.exchange_name, position.symbol)
