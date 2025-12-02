from typing import List, Optional

import numpy as np

import jesse.helpers as jh
from jesse.config import config
from jesse.enums import order_statuses, sides
from jesse.models.ClosedTrade import ClosedTrade
from jesse.models.Order import Order
from jesse.services.db import database


def _ensure_db_open() -> None:
    if not database.is_open():
        database.open_connection()


def find_by_id(trade_id: str) -> Optional[ClosedTrade]:
    if jh.is_unit_testing():
        return None

    _ensure_db_open()

    try:
        return ClosedTrade.select().where(ClosedTrade.id == trade_id).first()
    except Exception:
        return None


def find_by_session_id(session_id: str, limit: int = None) -> List[ClosedTrade]:
    if jh.is_unit_testing():
        return []

    _ensure_db_open()

    query = (
        ClosedTrade.select()
        .where(ClosedTrade.session_id == session_id)
        # Sort by: open trades first (closed_at IS NULL), then by most recent opened_at
        .order_by(ClosedTrade.closed_at.is_null(False), ClosedTrade.opened_at.desc())
    )
    
    if limit is not None:
        query = query.limit(limit)
    
    return list[ClosedTrade](query)


def create(trade_data: dict) -> Optional[ClosedTrade]:
    if jh.is_unit_testing():
        return None

    _ensure_db_open()

    d = {
        "id": trade_data.get("id"),
        "session_id": trade_data.get("session_id"),
        "strategy_name": trade_data.get("strategy_name"),
        "symbol": trade_data.get("symbol"),
        "exchange": trade_data.get("exchange"),
        "type": trade_data.get("type"),
        "timeframe": trade_data.get("timeframe"),
        "leverage": trade_data.get("leverage"),
        "created_at": trade_data.get("created_at", jh.now_to_timestamp()),
        "updated_at": trade_data.get("updated_at", jh.now_to_timestamp()),
        "session_mode": config["app"]["trading_mode"],
        "opened_at": trade_data.get("opened_at"),
    }

    if trade_data.get("closed_at") is not None:
        d["closed_at"] = trade_data.get("closed_at")

    try:
        ClosedTrade.insert(**d).execute()
        return ClosedTrade.get(ClosedTrade.id == d["id"])
    except Exception as e:
        jh.dump(f"Error storing closed trade in database: {e}")
        raise


def update(trade: ClosedTrade) -> None:
    if jh.is_unit_testing():
        return

    _ensure_db_open()

    d = {
        "updated_at": jh.now_to_timestamp(),
    }

    try:
        ClosedTrade.update(**d).where(ClosedTrade.id == trade.id).execute()
    except Exception as e:
        jh.dump(f"Error updating closed trade in database: {e}")
        raise


def store_or_update(trade: ClosedTrade) -> None:
    if jh.is_unit_testing():
        return

    _ensure_db_open()

    db_trade = ClosedTrade.select().where(ClosedTrade.id == trade.id).first()
    if db_trade:
        update(trade)
        return

    d = {
        "id": trade.id,
        "session_id": trade.session_id,
        "strategy_name": trade.strategy_name,
        "symbol": trade.symbol,
        "exchange": trade.exchange,
        "type": trade.type,
        "timeframe": trade.timeframe,
        "leverage": trade.leverage,
        "created_at": trade.created_at if hasattr(trade, "created_at") else jh.now_to_timestamp(),
        "updated_at": trade.updated_at if hasattr(trade, "updated_at") else jh.now_to_timestamp(),
        "session_mode": config["app"]["trading_mode"],
        "opened_at": trade.opened_at,
    }

    if trade.closed_at is not None:
        d["closed_at"] = trade.closed_at

    try:
        ClosedTrade.insert(**d).execute()
    except Exception as e:
        jh.dump(f"Error storing closed trade in database: {e}")


def close_trade(trade: ClosedTrade, opened_at: int = None) -> None:
    if jh.is_unit_testing():
        return

    _ensure_db_open()

    d = {
        "closed_at": trade.closed_at if trade.closed_at else jh.now_to_timestamp(),
        "updated_at": jh.now_to_timestamp(),
    }
    if opened_at:
        d["opened_at"] = opened_at
    try:
        ClosedTrade.update(**d).where(ClosedTrade.id == trade.id).execute()
    except Exception as e:
        jh.dump(f"Error closing trade in database: {e}")


def disable_trade(trade_id: str) -> None:
    if jh.is_unit_testing():
        return

    _ensure_db_open()

    d = {
        "soft_deleted_at": jh.now_to_timestamp(),
    }
    ClosedTrade.update(**d).where(ClosedTrade.id == trade_id).execute()


def get_open_trade(exchange_name: str, symbol: str, is_initial: bool = False) -> Optional[ClosedTrade]:
    if jh.is_unit_testing():
        return None

    _ensure_db_open()

    trade = (
        ClosedTrade.select()
        .where(ClosedTrade.soft_deleted_at == None)
        .where(ClosedTrade.session_mode == "livetrade")
        .where(ClosedTrade.exchange == exchange_name)
        .where(ClosedTrade.symbol == symbol)
        .where(ClosedTrade.closed_at == None)
        .order_by(ClosedTrade.opened_at.desc())
        .first()
    )

    if trade is None or not is_initial:
        return trade

    exchange_orders = list(
        Order.select()
        .where(Order.trade_id == trade.id)
        .where(Order.status == order_statuses.EXECUTED)
        .where(Order.order_exist_in_exchange == True)
        .order_by(Order.executed_at)
    )
    simulated_orders = list(
        Order.select()
        .where(Order.trade_id == trade.id)
        .where(Order.status == order_statuses.EXECUTED)
        .where(Order.order_exist_in_exchange == False)
        .order_by(Order.executed_at)
    )

    if len(exchange_orders) == 0:
        if len(simulated_orders) > 0:
            for simulated_order in simulated_orders:
                if simulated_order.side == sides.BUY:
                    trade.buy_orders.append(np.array([abs(simulated_order.filled_qty), simulated_order.price]))
                elif simulated_order.side == sides.SELL:
                    trade.sell_orders.append(np.array([abs(simulated_order.filled_qty), simulated_order.price]))
            trade.is_simulated = True
        return trade

    trade.orders = {order.exchange_id: order for order in exchange_orders if order.exchange_id}
    trade.is_simulated = False
    for o in exchange_orders + simulated_orders:
        if o.side == sides.BUY:
            trade.buy_orders.append(np.array([abs(o.filled_qty), o.price]))
        elif o.side == sides.SELL:
            trade.sell_orders.append(np.array([abs(o.filled_qty), o.price]))
    if trade.current_qty == 0:
        close_trade(trade)
        return None
    else:
        return trade

