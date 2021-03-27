import threading

import numpy as np

import jesse.helpers as jh
from jesse.models.Candle import Candle
from jesse.models.CompletedTrade import CompletedTrade
from jesse.models.DailyBalance import DailyBalance
from jesse.models.Order import Order
from jesse.models.Orderbook import Orderbook
from jesse.models.Ticker import Ticker
from jesse.models.Trade import Trade
from jesse.services import logger


def store_candle_into_db(exchange: str, symbol: str, candle: np.ndarray) -> None:
    d = {
        'id': jh.generate_unique_id(),
        'symbol': symbol,
        'exchange': exchange,
        'timestamp': candle[0],
        'open': candle[1],
        'high': candle[3],
        'low': candle[4],
        'close': candle[2],
        'volume': candle[5]
    }

    def async_save() -> None:
        Candle.insert(**d).on_conflict_ignore().execute()
        print(
            jh.color(
                f"candle: {jh.timestamp_to_time(d['timestamp'])}-{exchange}-{symbol}: {candle}",
                'blue'
            )
        )

    # async call
    threading.Thread(target=async_save).start()


def store_ticker_into_db(exchange: str, symbol: str, ticker: np.ndarray) -> None:
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


def store_completed_trade_into_db(completed_trade: CompletedTrade) -> None:
    d = {
        'id': completed_trade.id,
        'strategy_name': completed_trade.strategy_name,
        'symbol': completed_trade.symbol,
        'exchange': completed_trade.exchange,
        'type': completed_trade.type,
        'timeframe': completed_trade.timeframe,
        'entry_price': completed_trade.entry_price,
        'exit_price': completed_trade.exit_price,
        'take_profit_at': completed_trade.take_profit_at,
        'stop_loss_at': completed_trade.stop_loss_at,
        'qty': completed_trade.qty,
        'opened_at': completed_trade.opened_at,
        'closed_at': completed_trade.closed_at,
        'entry_candle_timestamp': completed_trade.entry_candle_timestamp,
        'exit_candle_timestamp': completed_trade.exit_candle_timestamp,
        'leverage': completed_trade.leverage,
    }

    def async_save() -> None:
        CompletedTrade.insert(**d).execute()
        if jh.is_debugging():
            logger.info(f'Stored the completed trade record for {completed_trade.exchange}-{completed_trade.symbol}-{completed_trade.strategy_name} into database.')

    # async call
    threading.Thread(target=async_save).start()


def store_order_into_db(order: Order) -> None:
    d = {
        'id': order.id,
        'trade_id': order.trade_id,
        'exchange_id': order.exchange_id,
        'vars': order.vars,
        'symbol': order.symbol,
        'exchange': order.exchange,
        'side': order.side,
        'type': order.type,
        'flag': order.flag,
        'qty': order.qty,
        'price': order.price,
        'status': order.status,
        'created_at': order.created_at,
        'executed_at': order.executed_at,
        'canceled_at': order.canceled_at,
        'role': order.role,
    }

    def async_save() -> None:
        Order.insert(**d).execute()
        if jh.is_debugging():
            logger.info(f'Stored the executed order record for {order.exchange}-{order.symbol} into database.')

    # async call
    threading.Thread(target=async_save).start()


def store_daily_balance_into_db(daily_balance: dict) -> None:
    def async_save():
        DailyBalance.insert(**daily_balance).execute()
        if jh.is_debugging():
            logger.info(f'Stored daily portfolio balance record into the database: {daily_balance["asset"]} => {jh.format_currency(round(daily_balance["balance"], 2))}'
            )

    # async call
    threading.Thread(target=async_save).start()


def store_trade_into_db(exchange: str, symbol: str, trade: np.ndarray) -> None:
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


def fetch_candles_from_db(exchange: str, symbol: str, start_date: int, finish_date: int) -> tuple:
    candles_tuple = tuple(
        Candle.select(
            Candle.timestamp, Candle.open, Candle.close, Candle.high, Candle.low,
            Candle.volume
        ).where(
            Candle.timestamp.between(start_date, finish_date),
            Candle.exchange == exchange,
            Candle.symbol == symbol
        ).order_by(Candle.timestamp.asc()).tuples()
    )

    return candles_tuple
