import jesse.helpers as jh
from jesse.services.notifier import notify, notify_urgently
import logging


# log id is also its index in the array which is helpful for pagination
id_info = 0
id_error = 0


def info(msg: str) -> None:
    global id_info
    msg = str(msg)
    from jesse.store import store

    store.logs.info.append({
        'id': id_info,
        'time': jh.now_to_timestamp(),
        'message': msg
    })

    id_info += 1

    if (jh.is_backtesting() and jh.is_debugging()) or jh.is_collecting_data():
        print(f'[{jh.timestamp_to_time(jh.now_to_timestamp())}]: {msg}')

    if jh.is_live():
        msg = f"[INFO | {jh.timestamp_to_time(jh.now_to_timestamp())[:19]}] {msg}"
        logging.info(msg)


def error(msg: str) -> None:
    global id_error
    msg = str(msg)
    from jesse.store import store

    if jh.is_live() and jh.get_config('env.notifications.events.errors', True):
        notify_urgently(f"ERROR at \"{jh.get_config('env.identifier')}\" account:\n{msg}")
        notify(f'ERROR:\n{msg}')
    if (jh.is_backtesting() and jh.is_debugging()) or jh.is_collecting_data():
        print(jh.color(f'[{jh.timestamp_to_time(jh.now_to_timestamp())}]: {msg}', 'red'))

    store.logs.errors.append({
        'id': id_error,
        'time': jh.now_to_timestamp(),
        'message': msg
    })

    id_error += 1

    if jh.is_live() or jh.is_optimizing():
        msg = f"[ERROR | {jh.timestamp_to_time(jh.now_to_timestamp())[:19]}] {msg}"
        logging.error(msg)
