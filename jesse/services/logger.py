import jesse.helpers as jh
from jesse.services.notifier import notify, notify_urgently
from jesse.services.redis import sync_publish
import logging


def info(msg: str) -> None:
    msg = str(msg)
    from jesse.store import store

    store.logs.info.append({
        'id': store.app.id_info,
        'time': jh.now_to_timestamp(),
        'message': msg
    })

    store.app.id_info += 1

    if (jh.is_backtesting() and jh.is_debugging()) or jh.is_collecting_data() or jh.is_live():
        sync_publish('info_log', {
            'id': store.app.id_info,
            'time': jh.now_to_timestamp(),
            'message': msg
        })

    if jh.is_live():
        msg = f"[INFO | {jh.timestamp_to_time(jh.now_to_timestamp())[:19]}] {msg}"
        logging.info(msg)


def error(msg: str) -> None:
    msg = str(msg)
    from jesse.store import store

    if jh.is_live() and jh.get_config('env.notifications.events.errors', True):
        notify_urgently(f"ERROR at \"{jh.get_config('env.identifier')}\" account:\n{msg}")
        notify(f'ERROR:\n{msg}')
    if (jh.is_backtesting() and jh.is_debugging()) or jh.is_collecting_data() or jh.is_live():
        sync_publish('error_log', {
            'id': store.app.id_error,
            'time': jh.now_to_timestamp(),
            'message': msg
        })

    store.logs.errors.append({
        'id': store.app.id_error,
        'time': jh.now_to_timestamp(),
        'message': msg
    })

    store.app.id_error += 1

    if jh.is_live() or jh.is_optimizing():
        msg = f"[ERROR | {jh.timestamp_to_time(jh.now_to_timestamp())[:19]}] {msg}"
        logging.error(msg)
