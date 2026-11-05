import jesse.helpers as jh
from jesse.services import logger, notifier
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

    # Some exchanges (e.g. Binance) report filled_qty as a *cumulative* running total
    # across partial fills. If we appended that value on every call we'd inflate qty
    # and therefore PNL. Instead, we track how much has already been recorded for this
    # order and only append the incremental amount.
    prev_recorded: float = getattr(order, '_recorded_fill_qty', 0.0)
    current_fill: float = abs(order.filled_qty or 0.0)
    incremental: float = current_fill - prev_recorded

    if incremental <= 0:
        return

    order._recorded_fill_qty = current_fill

    if order.side == sides.BUY:
        t.buy_orders.append(np.array([incremental, order.price]))
    elif order.side == sides.SELL:
        t.sell_orders.append(np.array([incremental, order.price]))
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


def restore_open_trade(position: Position, trade: ClosedTrade) -> None:
    """Attach the persisted trade and its fills to the restored live position."""
    # Hydrate once so repeat reconciliation cannot duplicate fills or their fees.
    if not trade.orders and len(trade.buy_orders) == 0 and len(trade.sell_orders) == 0:
        closed_trade_repository.hydrate_executed_orders(trade)
    if trade.opened_at is None:
        trade.opened_at = position.opened_at
    try:
        trade.timeframe = position.strategy.timeframe
        trade.strategy_name = position.strategy.name
    except AttributeError:
        if not jh.is_unit_testing():
            raise
    store.closed_trades.tempt_trades[jh.key(position.exchange_name, position.symbol)] = trade


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
    store.closed_trades.record_closure(t)
    closed_trade_repository.close_trade(t)
    currency = position.exchange.settlement_currency.upper()
    outcome = '🟢' if t.pnl > 0 else '🔴' if t.pnl < 0 else '⚪'
    message = (
        f'{outcome} Trade closed | {t.symbol} | {t.type.upper()} | {store.app.exchange_label(t.exchange)}\n'
        f'Qty: {t.qty} | Entry: {jh.format_price(t.entry_price)} | Exit: {jh.format_price(t.exit_price)}\n'
        f'Net PnL: {t.pnl:+.2f} {currency} ({t.pnl_percentage:+.2f}%) | Fees: {jh.format_price(t.fee)} {currency}'
    )
    if not jh.is_unit_testing():
        logger.info(message)
    # Finalized trade data includes all fills and fees. Send once here, rather than
    # emitting a second, incomplete close notification from the strategy callback.
    if jh.is_live() and jh.get_config(
        'env.notifications.events.closed_position',
        jh.get_config('env.notifications.events.updated_position', True),
    ):
        notifier.notify(message)
    store.closed_trades._reset_current_trade(position.exchange_name, position.symbol)
