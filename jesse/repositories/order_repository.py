from typing import Optional, List, Tuple
import numpy as np
import jesse.helpers as jh
from peewee import Cast
from jesse.models import Candle
from jesse.models.Order import Order
from jesse.enums import order_statuses
from jesse.config import config
from jesse.store import store
from jesse.services.db import database


def create(order_data: dict) -> Order:
    if jh.is_unit_testing():
        return None

    if not database.is_open():
        database.open_connection()
        
    d = {
        'id': order_data.get('id'),
        'session_id': store.app.session_id,
        'symbol': order_data.get('symbol'),
        'exchange': order_data.get('exchange'),
        'side': order_data.get('side'),
        'type': order_data.get('type'),
        'reduce_only': order_data.get('reduce_only'),
        'qty': order_data.get('qty'),
        'status': order_data.get('status'),
        'created_at': order_data.get('created_at', jh.now_to_timestamp()),
        'updated_at': order_data.get('updated_at', jh.now_to_timestamp()),
        'session_mode': config['app']['trading_mode'],
    }
    
    if 'trade_id' in order_data and order_data.get('trade_id'):
        d['trade_id'] = order_data['trade_id']
    if 'executed_at' in order_data and order_data.get('executed_at'):
        d['executed_at'] = order_data['executed_at']
    if 'filled_qty' in order_data:
        d['filled_qty'] = order_data.get('filled_qty')
    if 'price' in order_data:
        d['price'] = order_data.get('price')
    if 'submitted_via' in order_data and order_data.get('submitted_via'):
        d['submitted_via'] = order_data['submitted_via']
    if 'jesse_submitted' in order_data:
        d['jesse_submitted'] = order_data.get('jesse_submitted')
    if 'exchange_id' in order_data and order_data.get('exchange_id'):
        d['exchange_id'] = order_data['exchange_id']
    if 'order_exist_in_exchange' in order_data:
        d['order_exist_in_exchange'] = order_data.get('order_exist_in_exchange')
    if 'canceled_at' in order_data and order_data.get('canceled_at'):
        d['canceled_at'] = order_data['canceled_at']
    
    try:
        Order.insert(**d).execute()
        return Order.get(Order.id == d['id'])
    except Exception as e:
        try:
            database.db.rollback()
        except Exception:
            pass
        jh.dump(f"Error storing order in database: {e}")
        raise


def update(order: Order) -> None:
    if jh.is_unit_testing():
        return

    if not database.is_open():
        database.open_connection()
        
    db_order = None
    if order.exchange_id:
        db_order = Order.select().where(Order.exchange_id == str(order.exchange_id)).first()
    if db_order is None and order.id:
        try:
            db_order = Order.select().where(Order.id == order.id).first()
        except Exception:
            try:
                database.db.rollback()
            except Exception:
                pass
            matches = find_by_partial_id(str(order.id), order.exchange, order.symbol)
            if matches and len(matches) == 1:
                db_order = matches[0]

    if db_order:
        d = {
            'updated_at': jh.now_to_timestamp(),
            'status': order.status,
            'filled_qty': order.filled_qty,
            'price': db_order.price if order.price == 0 else order.price,
            'exchange_id': order.exchange_id,
        }
        
        if order.is_executed:
            d['executed_at'] = getattr(order, 'executed_at', jh.now_to_timestamp())
        if order.is_canceled:
            d['canceled_at'] = jh.now_to_timestamp()
        if order.trade_id:
            d['trade_id'] = order.trade_id
        if order.submitted_via:
            d['submitted_via'] = order.submitted_via
        if order.qty != 0:
            d['qty'] = order.qty
        if order.fee:
            d['fee'] = order.fee
        try:
            Order.update(**d).where(Order.id == db_order.id).execute()
        except Exception as e:
            try:
                database.db.rollback()
            except Exception:
                pass
            jh.dump(f"Error updating order in database: {e}")
            raise


def store_or_update(order: Order) -> None:
    if jh.is_unit_testing():
        return

    if not database.is_open():
        database.open_connection()
        
    order_exist = False
    try:
        if order.exchange_id:
            order_exist = Order.select().where(Order.exchange_id == str(order.exchange_id)).first()
        if not order_exist and order.id:
            order_exist = Order.select().where(Order.id == order.id).first()
        if not order_exist and order.id and len(str(order.id)) <= 20:
            potential_matches = find_by_partial_id(str(order.id), order.exchange, order.symbol)
            if potential_matches and len(potential_matches) == 1:
                order_exist = potential_matches[0]
    except Exception as e:
        order_exist = False
    
    if order_exist:
        order.id = order_exist.id
        update(order)
        return
    
    d = {
        'id': order.id,
        'session_id': store.app.session_id,
        'symbol': order.symbol,
        'exchange': order.exchange,
        'side': order.side,
        'type': order.type,
        'reduce_only': order.reduce_only,
        'qty': order.qty,
        'status': order.status,
        'created_at': order.created_at if order.created_at else jh.now_to_timestamp(),
        'updated_at': order.updated_at if order.updated_at else jh.now_to_timestamp(),
        'session_mode': config['app']['trading_mode'],
    }
    if hasattr(order, 'trade_id'):
        d['trade_id'] = order.trade_id
    if hasattr(order, 'executed_at'):
        d['executed_at'] = order.executed_at
    if hasattr(order, 'filled_qty'):
        d['filled_qty'] = order.filled_qty
    if hasattr(order, 'price'):
        d['price'] = order.price
    if order.submitted_via:
        d['submitted_via'] = order.submitted_via
    if hasattr(order, 'jesse_submitted'):
        d['jesse_submitted'] = order.jesse_submitted
    if hasattr(order, 'exchange_id'):
        d['exchange_id'] = order.exchange_id
    if hasattr(order, 'order_exist_in_exchange'):
        d['order_exist_in_exchange'] = order.order_exist_in_exchange
    if hasattr(order, 'canceled_at'):
        d['canceled_at'] = order.canceled_at
    if hasattr(order, 'fee'):
        d['fee'] = order.fee
    
    try:
        Order.insert(**d).execute()
    except Exception as e:
        try:
            database.db.rollback()
        except Exception:
            pass
        jh.dump(f"Error storing order in database: {e}")


def find_by_id(order_id: str) -> Optional[Order]:
    if jh.is_unit_testing():
        return None

    if not database.is_open():
        database.open_connection()

    try:
        return Order.select().where(Order.id == order_id).first()
    except Exception:
        return None


def find_by_exchange_id(exchange_id: str) -> Optional[Order]:
    if jh.is_unit_testing():
        return None

    if not database.is_open():
        database.open_connection()

    try:
        return Order.select().where(Order.exchange_id == exchange_id).first()
    except Exception:
        return None


def find_by_exchange_or_client_id(order_dict: dict) -> Optional[Order]:
    if jh.is_unit_testing():
        return None

    if not database.is_open():
        database.open_connection()

    exchange_id = order_dict.get('exchange_id') if 'exchange_id' in order_dict else None
    client_id = order_dict.get('client_id') if 'client_id' in order_dict else None
    order = None
    if exchange_id:
        order = Order.select().where(Order.exchange_id == exchange_id).first()
    if not order and client_id:
        order = Order.select().where(Order.id == client_id).first()
        if not order:
            # UUID fields can't be searched with ILIKE directly; cast to text first.
            order = Order.select().where(Cast(Order.id, 'text').contains(client_id)).first()
    return order


def find_by_partial_id(partial_id: str, exchange: str = None, symbol: str = None) -> List[Order]:
    if jh.is_unit_testing():
        return []

    if not database.is_open():
        database.open_connection()

    # UUID fields can't be searched with ILIKE directly; cast to text first.
    query = Order.select().where(Cast(Order.id, 'text').contains(partial_id))
    
    if exchange:
        query = query.where(Order.exchange == exchange)
    if symbol:
        query = query.where(Order.symbol == symbol)
    
    return list(query)


def find_by_trade_id(trade_id: str) -> List[Order]:
    if jh.is_unit_testing():
        return []

    if not database.is_open():
        database.open_connection()

    return list(Order.select().where(Order.trade_id == trade_id))


def get_active_orders(symbol: str, exchange: str) -> List[Order]:
    if jh.is_unit_testing():
        return []

    if not database.is_open():
        database.open_connection()

    from jesse.models.ClosedTrade import ClosedTrade
    
    orders = Order.select().where(
        Order.symbol == symbol,
        Order.status == order_statuses.ACTIVE,
        Order.exchange == exchange
    )
    
    for order in orders:
        if order.trade_id:
            order.trade = ClosedTrade.get_trade_by_id(order.trade_id)
    return list(orders)


def get_executed_and_active_orders_without_trade_id(symbol: str, exchange: str) -> Tuple[List[Order], List[Order]]:
    if jh.is_unit_testing():
        return [], []

    if not database.is_open():
        database.open_connection()

    executed_orders = list(Order.select().where(
        Order.symbol == symbol,
        (Order.status == order_statuses.EXECUTED),
        Order.exchange == exchange,
        Order.trade_id == None,
        Order.order_exist_in_exchange == True
    ).order_by(
        Order.executed_at.asc()
    ))
    active_orders = list(Order.select().where(
        Order.symbol == symbol,
        (Order.status == order_statuses.ACTIVE),
        Order.exchange == exchange,
        Order.order_exist_in_exchange == True
    ).order_by(
        Order.created_at.asc()
    ))
    return executed_orders, active_orders


def get_session_orders(session_id: str, exchange: str, symbol: str) -> List[Order]:
    if jh.is_unit_testing():
        return []

    if not database.is_open():
        database.open_connection()

    return list(Order.select().where(
        Order.session_id == session_id,
        Order.exchange == exchange,
        Order.symbol == symbol
    ))


def get_last_exchange_order(exchange: str, symbol: str) -> Optional[Order]:
    if jh.is_unit_testing():
        return None

    if not database.is_open():
        database.open_connection()

    return Order.select().where(
        Order.exchange == exchange,
        Order.symbol == symbol
    ).where(
        Order.trade_id != None
    ).where(
        Order.order_exist_in_exchange == True
    ).order_by(
        Order.created_at.desc()
    ).first()


def get_simulated_orders(exchange: str, symbol: str, qty: float = None) -> List[Order]:
    if jh.is_unit_testing():
        return []

    if not database.is_open():
        database.open_connection()

    query = Order.select().where(
        Order.exchange == exchange,
        Order.symbol == symbol,
        Order.order_exist_in_exchange == False
    )
    if qty:
        query = query.where(Order.qty == qty)
    return list(query.order_by(Order.created_at.desc()))


def find_by_filters(
    id_search: str = None,
    status_filter: str = None,
    symbol_filter: str = None,
    date_filter: str = None,
    exchange_filter: str = None,
    type_filter: str = None,
    side_filter: str = None,
    limit: int = 50,
    offset: int = 0
) -> List[Order]:
    if jh.is_unit_testing():
        return []

    if not database.is_open():
        database.open_connection()

    # If a previous query failed, the connection can be left in an aborted transaction state.
    # Rolling back here ensures subsequent SELECTs work.
    try:
        database.db.rollback()
    except Exception:
        pass

    query = Order.select()

    if id_search:
        # UUID fields can't be searched with ILIKE directly; cast to text first.
        query = query.where(
            (Cast(Order.id, 'text').contains(id_search)) |
            (Cast(Order.session_id, 'text').contains(id_search)) |
            (Order.exchange_id.contains(id_search))
        )

    if status_filter:
        query = query.where(Order.status == status_filter)

    if symbol_filter:
        query = query.where(Order.symbol.contains(symbol_filter))

    if exchange_filter:
        query = query.where(Order.exchange.contains(exchange_filter))

    if type_filter:
        query = query.where(Order.type.contains(type_filter))

    if side_filter:
        query = query.where(Order.side.contains(side_filter))

    if date_filter:
        cutoff_timestamp = jh.now_to_timestamp()
        if date_filter == '7_days':
            cutoff_timestamp -= 7 * 24 * 60 * 60 * 1000
        elif date_filter == '30_days':
            cutoff_timestamp -= 30 * 24 * 60 * 60 * 1000
        elif date_filter == '90_days':
            cutoff_timestamp -= 90 * 24 * 60 * 60 * 1000

        if date_filter != 'all_time':
            query = query.where(Order.created_at >= cutoff_timestamp)

    query = query.order_by(Order.created_at.desc()).limit(limit).offset(offset)

    try:
        return list(query)
    except Exception:
        # Ensure we don't poison the connection for subsequent requests.
        try:
            database.db.rollback()
        except Exception:
            pass
        raise


def delete(order_id: str) -> None:
    if jh.is_unit_testing():
        return

    if not database.is_open():
        database.open_connection()

    Order.delete().where(Order.id == order_id).execute()
