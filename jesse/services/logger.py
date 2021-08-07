import jesse.helpers as jh
from jesse.services.notifier import notify, notify_urgently
from jesse.services.redis import sync_publish
import logging
from jesse.models.utils import store_log_into_db


def info(msg: str) -> None:
    msg = str(msg)
    from jesse.store import store

    log_id = jh.generate_unique_id()
    log_dict = {
        'id': log_id,
        'timestamp': jh.now_to_timestamp(),
        'message': msg
    }

    store.logs.info.append(log_dict)

    if (jh.is_backtesting() and jh.is_debugging()) or jh.is_collecting_data() or jh.is_live():
        sync_publish('info_log', log_dict)

    if jh.is_live():
        msg = f"[INFO | {jh.timestamp_to_time(jh.now_to_timestamp())[:19]}] {msg}"
        logging.info(msg)

        store_log_into_db(log_dict, 'info')


def error(msg: str) -> None:
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
        logging.error(msg)

    if jh.is_live():
        store_log_into_db(log_dict, 'error')
