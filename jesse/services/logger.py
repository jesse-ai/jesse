import jesse.helpers as jh
from jesse.services.notifier import notify, notify_urgently
from jesse.services.redis import sync_publish
import logging
import os

# store loggers in the dict because we might want to add more later
LOGGERS = {}


def _init_main_logger():
    session_id = jh.get_session_id()
    jh.make_directory('storage/logs/live-mode')
    jh.make_directory('storage/logs/backtest-mode')
    jh.make_directory('storage/logs/optimize-mode')
    jh.make_directory('storage/logs/collect-mode')

    if jh.is_live():
        filename = f'storage/logs/live-mode/{session_id}.txt'
    elif jh.is_collecting_data():
        filename = f'storage/logs/collect-mode/{session_id}.txt'
    elif jh.is_optimizing():
        filename = f'storage/logs/optimize-mode/{session_id}.txt'
    elif jh.is_backtesting():
        filename = f'storage/logs/backtest-mode/{session_id}.txt'
    else:
        filename = 'storage/logs/etc.txt'

    new_logger = logging.getLogger(jh.app_mode())
    new_logger.setLevel(logging.INFO)
    new_logger.addHandler(logging.FileHandler(filename, mode='w'))
    LOGGERS[jh.app_mode()] = new_logger


def create_disposable_logger(name):
    log_file = f"storage/logs/{name}.txt"
    os.makedirs('storage/logs', exist_ok=True)
    new_logger = logging.getLogger(name)
    new_logger.setLevel(logging.INFO)
    new_logger.addHandler(logging.FileHandler(log_file, mode='w'))
    LOGGERS[name] = new_logger


def create_logger_file(name):
    log_file = f"storage/logs/{name}.txt"
    os.makedirs('storage/logs', exist_ok=True)
    new_logger = logging.getLogger(name)
    new_logger.setLevel(logging.INFO)
    # should add to the end of file
    new_logger.addHandler(logging.FileHandler(log_file, mode='a'))
    LOGGERS[name] = new_logger


def info(msg: str, send_notification=False) -> None:
    if jh.app_mode() not in LOGGERS:
        _init_main_logger()

    msg = str(msg)
    from jesse.store import store

    log_id = jh.generate_unique_id()
    log_dict = {
        'id': log_id,
        'timestamp': jh.now_to_timestamp(),
        'message': msg
    }

    store.logs.info.append(log_dict)

    if jh.is_collecting_data() or jh.is_live():
        sync_publish('info_log', log_dict)

    if jh.is_live() or (jh.is_backtesting() and jh.is_debugging()):
        msg = f"[INFO | {jh.timestamp_to_time(jh.now_to_timestamp())[:19]}] {msg}"
        logger = LOGGERS[jh.app_mode()]
        logger.info(msg)

    if jh.is_live():
        from jesse.models.utils import store_log_into_db
        store_log_into_db(log_dict, 'info')

    if send_notification:
        notify(msg)


def error(msg: str) -> None:
    if jh.app_mode() not in LOGGERS:
        _init_main_logger()

    # error logs should be logged as info logs as well
    info(msg)

    msg = str(msg)
    from jesse.store import store

    log_id = jh.generate_unique_id()
    log_dict = {
        'id': log_id,
        'timestamp': jh.now_to_timestamp(),
        'message': msg
    }

    if jh.is_live() and jh.get_config('env.notifications.events.errors', True):
        # notify_urgently(f"ERROR at \"{jh.get_config('env.identifier')}\" account:\n{msg}")
        notify_urgently(f"ERROR:\n{msg}")
        notify(f'ERROR:\n{msg}')
    if (jh.is_backtesting() and jh.is_debugging()) or jh.is_collecting_data() or jh.is_live():
        sync_publish('error_log', log_dict)

    store.logs.errors.append(log_dict)

    if jh.is_live() or jh.is_optimizing():
        msg = f"[ERROR | {jh.timestamp_to_time(jh.now_to_timestamp())[:19]}] {msg}"
        logger = LOGGERS[jh.app_mode()]
        logger.error(msg)

    if jh.is_live():
        from jesse.models.utils import store_log_into_db
        store_log_into_db(log_dict, 'error')


def log_exchange_message(exchange, message):
    # if the type of message is not str, convert it to str
    if not isinstance(message, str):
        message = str(message)

    formatted_time = jh.timestamp_to_time(jh.now())[:19]
    message = f'[{formatted_time} - {exchange}]: ' + message

    if 'exchange-streams' not in LOGGERS:
        create_disposable_logger('exchange-streams')

    LOGGERS['exchange-streams'].info(message)


def log_optimize_mode(message):
    # if the type of message is not str, convert it to str
    if not isinstance(message, str):
        message = str(message)

    formatted_time = jh.timestamp_to_time(jh.now())[:19]
    message = f'[{formatted_time}]: ' + message
    file_name = 'optimize-mode'

    if file_name not in LOGGERS:
        create_logger_file(file_name)

    LOGGERS[file_name].info(message)


def broadcast_error_without_logging(msg: str):
    msg = str(msg)

    sync_publish('error_log', {
        'id': jh.generate_unique_id(),
        'timestamp': jh.now_to_timestamp(),
        'message': msg
    })
