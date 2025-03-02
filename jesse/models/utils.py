import threading
import numpy as np

import jesse.helpers as jh
from jesse.services import logger


def store_optimization_session(
    session_id: str,
    status: str,
    config: dict,
    training_start_date: int,
    training_finish_date: int,
    testing_start_date: int,
    testing_finish_date: int,
    total_trials: int
) -> None:
    """
    Create a new optimization session in the database
    
    Parameters
    ----------
    session_id : str
        Unique identifier for the session
    status : str
        Status of the session (running, paused, finished, stopped)
    config : dict
        Configuration parameters for the optimization
    training_start_date : int
        Start timestamp for training period
    training_finish_date : int
        End timestamp for training period
    testing_start_date : int
        Start timestamp for testing period
    testing_finish_date : int
        End timestamp for testing period
    total_trials : int
        Total number of trials to run
    """
    from jesse.models.OptimizationSession import OptimizationSession
    import json
    
    # Create session object
    session = OptimizationSession(
        id=session_id,
        status=status,
        config=json.dumps(config),
        training_start_date=training_start_date,
        training_finish_date=training_finish_date,
        testing_start_date=testing_start_date,
        testing_finish_date=testing_finish_date,
        completed_trials=0,
        total_trials=total_trials,
        created_at=jh.now_to_timestamp(),
    )
    
    # Save to database
    session.save()
    
    if jh.is_debugging():
        logger.info(f'Created optimization session with ID: {session_id}')


def update_optimization_session_status(session_id: str, status: str) -> None:
    """
    Update the status of an optimization session
    
    Parameters
    ----------
    session_id : str
        ID of the session to update
    status : str
        New status (running, paused, finished, stopped)
    """
    from jesse.models.OptimizationSession import OptimizationSession
    
    try:
        session = OptimizationSession.get(OptimizationSession.id == session_id)
        session.status = status
        session.updated_at = jh.now_to_timestamp()
        session.save()
        
        if jh.is_debugging():
            logger.info(f'Updated optimization session {session_id} status to: {status}')
    except OptimizationSession.DoesNotExist:
        logger.error(f'Cannot update status: Optimization session with ID {session_id} not found')


def update_optimization_session_trials(
    session_id: str, 
    completed_trials: int, 
    best_trials: list = None,
    objective_curve: list = None
) -> None:
    """
    Update the trials information for an optimization session
    
    Parameters
    ----------
    session_id : str
        ID of the session to update
    completed_trials : int
        Number of completed trials
    best_trials : list, optional
        List of best trial objects
    objective_curve : list, optional
        List of objective curve data points
    """
    from jesse.models.OptimizationSession import OptimizationSession
    import json
    
    try:
        session = OptimizationSession.get(OptimizationSession.id == session_id)
        session.completed_trials = completed_trials
        
        if best_trials is not None:
            session.best_trials = json.dumps(best_trials)
            
        if objective_curve is not None:
            session.objective_curve = json.dumps(objective_curve)
            
        session.updated_at = jh.now_to_timestamp()
        session.save()
        
        if jh.is_debugging():
            logger.info(f'Updated optimization session {session_id} with {completed_trials} completed trials')
    except OptimizationSession.DoesNotExist:
        logger.error(f'Cannot update trials: Optimization session with ID {session_id} not found')


def get_optimization_session(session_id: str) -> dict:
    """
    Get an optimization session by ID
    
    Parameters
    ----------
    session_id : str
        ID of the session to retrieve
        
    Returns
    -------
    dict
        Session data as a dictionary, or None if not found
    """
    from jesse.models.OptimizationSession import OptimizationSession
    
    try:
        session = OptimizationSession.get(OptimizationSession.id == session_id)
        return {
            'id': session.id,
            'status': session.status,
            'config': session.config_json,
            'best_trials': session.best_trials_json,
            'objective_curve': session.objective_curve_json,
            'completed_trials': session.completed_trials,
            'total_trials': session.total_trials,
            'training_start_date': session.training_start_date,
            'training_finish_date': session.training_finish_date,
            'testing_start_date': session.testing_start_date,
            'testing_finish_date': session.testing_finish_date,
            'created_at': session.created_at,
            'updated_at': session.updated_at,
            'duration': session.duration,
            'best_score': session.best_score
        }
    except OptimizationSession.DoesNotExist:
        logger.error(f'Optimization session with ID {session_id} not found')
        return None


def get_optimization_sessions(status: str = None, limit: int = 20, offset: int = 0) -> list:
    """
    Get a list of optimization sessions, optionally filtered by status
    
    Parameters
    ----------
    status : str, optional
        Filter by status (running, paused, finished, stopped)
    limit : int, optional
        Maximum number of sessions to return
    offset : int, optional
        Number of sessions to skip
        
    Returns
    -------
    list
        List of session dictionaries
    """
    from jesse.models.OptimizationSession import OptimizationSession
    
    query = OptimizationSession.select().order_by(OptimizationSession.created_at.desc()).limit(limit).offset(offset)
    
    if status:
        query = query.where(OptimizationSession.status == status)
    
    sessions = []
    for session in query:
        sessions.append({
            'id': session.id,
            'status': session.status,
            'config': session.config_json,
            'completed_trials': session.completed_trials,
            'total_trials': session.total_trials,
            'created_at': session.created_at,
            'updated_at': session.updated_at,
            'duration': session.duration,
            'best_score': session.best_score
        })
    
    return sessions


def delete_optimization_session(session_id: str) -> bool:
    """
    Delete an optimization session
    
    Parameters
    ----------
    session_id : str
        ID of the session to delete
        
    Returns
    -------
    bool
        True if successful, False otherwise
    """
    from jesse.models.OptimizationSession import OptimizationSession
    
    try:
        session = OptimizationSession.get(OptimizationSession.id == session_id)
        session.delete_instance()
        
        if jh.is_debugging():
            logger.info(f'Deleted optimization session with ID: {session_id}')
        
        return True
    except OptimizationSession.DoesNotExist:
        logger.error(f'Cannot delete: Optimization session with ID {session_id} not found')
        return False


def store_candle_into_db(exchange: str, symbol: str, timeframe: str, candle: np.ndarray, on_conflict='ignore') -> None:
    from jesse.models.Candle import Candle

    d = {
        'id': jh.generate_unique_id(),
        'exchange': exchange,
        'symbol': symbol,
        'timeframe': timeframe,
        'timestamp': candle[0],
        'open': candle[1],
        'high': candle[3],
        'low': candle[4],
        'close': candle[2],
        'volume': candle[5]
    }

    if on_conflict == 'ignore':
        Candle.insert(**d).on_conflict_ignore().execute()
    elif on_conflict == 'replace':
        Candle.insert(**d).on_conflict(
            conflict_target=['exchange', 'symbol', 'timeframe', 'timestamp'],
            preserve=(Candle.open, Candle.high, Candle.low, Candle.close, Candle.volume),
        ).execute()
    elif on_conflict == 'error':
        Candle.insert(**d).execute()
    else:
        raise Exception(f'Unknown on_conflict value: {on_conflict}')


def store_candles_into_db(exchange: str, symbol: str, timeframe: str, candles: np.ndarray, on_conflict='ignore') -> None:
    # make sure the number of candles is more than 0
    if len(candles) == 0:
        raise Exception(f'No candles to store for {exchange}-{symbol}-{timeframe}')

    from jesse.models import Candle

    # convert candles to list of dicts
    candles_list = []
    for candle in candles:
        d = {
            'id': jh.generate_unique_id(),
            'symbol': symbol,
            'exchange': exchange,
            'timestamp': candle[0],
            'open': candle[1],
            'high': candle[3],
            'low': candle[4],
            'close': candle[2],
            'volume': candle[5],
            'timeframe': timeframe,
        }
        candles_list.append(d)

    if on_conflict == 'ignore':
        Candle.insert_many(candles_list).on_conflict_ignore().execute()
    elif on_conflict == 'replace':
        Candle.insert_many(candles_list).on_conflict(
            conflict_target=['exchange', 'symbol', 'timeframe', 'timestamp'],
            preserve=(Candle.open, Candle.high, Candle.low, Candle.close, Candle.volume),
        ).execute()
    elif on_conflict == 'error':
        Candle.insert_many(candles_list).execute()
    else:
        raise Exception(f'Unknown on_conflict value: {on_conflict}')


def store_log_into_db(log: dict, log_type: str) -> None:
    from jesse.store import store
    from jesse.models.Log import Log

    if log_type == 'info':
        log_type = 1
    elif log_type == 'error':
        log_type = 2
    else:
        raise ValueError(f"Unsupported log_type value: {log_type}")

    d = {
        'id': log['id'],
        'session_id': store.app.session_id,
        'type': log_type,
        'timestamp': log['timestamp'],
        'message': log['message']
    }

    Log.insert(**d).execute()


def store_ticker_into_db(exchange: str, symbol: str, ticker: np.ndarray) -> None:
    return
    from jesse.models.Ticker import Ticker

    d = {
        'id': jh.generate_unique_id(),
        'timestamp': ticker[0],
        'last_price': ticker[1],
        'high_price': ticker[2],
        'low_price': ticker[3],
        'volume': ticker[4],
        'symbol': symbol,
        'exchange': exchange,
    }

    def async_save() -> None:
        Ticker.insert(**d).on_conflict_ignore().execute()
        print(
            jh.color(f'ticker: {jh.timestamp_to_time(d["timestamp"])}-{exchange}-{symbol}: {ticker}', 'yellow')
        )

    # async call
    threading.Thread(target=async_save).start()


def store_completed_trade_into_db(completed_trade) -> None:
    return
    from jesse.models.ClosedTrade import ClosedTrade

    d = {
        'id': completed_trade.id,
        'strategy_name': completed_trade.strategy_name,
        'symbol': completed_trade.symbol,
        'exchange': completed_trade.exchange,
        'type': completed_trade.type,
        'timeframe': completed_trade.timeframe,
        'entry_price': completed_trade.entry_price,
        'exit_price': completed_trade.exit_price,
        'qty': completed_trade.qty,
        'opened_at': completed_trade.opened_at,
        'closed_at': completed_trade.closed_at,
        'leverage': completed_trade.leverage,
    }

    def async_save() -> None:
        ClosedTrade.insert(**d).execute()
        if jh.is_debugging():
            logger.info(
                f'Stored the completed trade record for {completed_trade.exchange}-{completed_trade.symbol}-{completed_trade.strategy_name} into database.')

    # async call
    threading.Thread(target=async_save).start()


def store_order_into_db(order) -> None:
    return
    from jesse.models.Order import Order

    d = {
        'id': order.id,
        'trade_id': order.trade_id,
        'exchange_id': order.exchange_id,
        'vars': order.vars,
        'symbol': order.symbol,
        'exchange': order.exchange,
        'side': order.side,
        'type': order.type,
        'reduce_only': order.reduce_only,
        'qty': order.qty,
        'filled_qty': order.filled_qty,
        'price': order.price,
        'status': order.status,
        'created_at': order.created_at,
        'executed_at': order.executed_at,
        'canceled_at': order.canceled_at,
    }

    def async_save() -> None:
        Order.insert(**d).execute()
        if jh.is_debugging():
            logger.info(f'Stored the executed order record for {order.exchange}-{order.symbol} into database.')

    # async call
    threading.Thread(target=async_save).start()


def store_daily_balance_into_db(daily_balance: dict) -> None:
    return
    from jesse.models.DailyBalance import DailyBalance

    def async_save():
        DailyBalance.insert(**daily_balance).execute()
        if jh.is_debugging():
            logger.info(
                f'Stored daily portfolio balance record into the database: {daily_balance["asset"]} => {jh.format_currency(round(daily_balance["balance"], 2))}'
                )

    # async call
    threading.Thread(target=async_save).start()


def store_trade_into_db(exchange: str, symbol: str, trade: np.ndarray) -> None:
    return
    from jesse.models.Trade import Trade

    d = {
        'id': jh.generate_unique_id(),
        'timestamp': trade[0],
        'price': trade[1],
        'buy_qty': trade[2],
        'sell_qty': trade[3],
        'buy_count': trade[4],
        'sell_count': trade[5],
        'symbol': symbol,
        'exchange': exchange,
    }

    def async_save() -> None:
        Trade.insert(**d).on_conflict_ignore().execute()
        print(
            jh.color(
                f'trade: {jh.timestamp_to_time(d["timestamp"])}-{exchange}-{symbol}: {trade}',
                'green'
            )
        )

    # async call
    threading.Thread(target=async_save).start()


def store_orderbook_into_db(exchange: str, symbol: str, orderbook: np.ndarray) -> None:
    return
    from jesse.models.Orderbook import Orderbook

    d = {
        'id': jh.generate_unique_id(),
        'timestamp': jh.now_to_timestamp(),
        'data': orderbook.dumps(),
        'symbol': symbol,
        'exchange': exchange,
    }

    def async_save() -> None:
        Orderbook.insert(**d).on_conflict_ignore().execute()
        print(
            jh.color(
                f'orderbook: {jh.timestamp_to_time(d["timestamp"])}-{exchange}-{symbol}: [{orderbook[0][0][0]}, {orderbook[0][0][1]}], [{orderbook[1][0][0]}, {orderbook[1][0][1]}]',
                'magenta'
            )
        )

    # async call
    threading.Thread(target=async_save).start()


def fetch_candles_from_db(exchange: str, symbol: str, timeframe: str, start_date: int, finish_date: int) -> tuple:
    from jesse.models.Candle import Candle

    res = tuple(
        Candle.select(
            Candle.timestamp, Candle.open, Candle.close, Candle.high, Candle.low,
            Candle.volume
        ).where(
            Candle.exchange == exchange,
            Candle.symbol == symbol,
            Candle.timeframe == timeframe,
            Candle.timestamp.between(start_date, finish_date)
        ).order_by(Candle.timestamp.asc()).tuples()
    )

    return res
