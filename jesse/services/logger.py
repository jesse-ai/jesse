import jesse.helpers as jh
from jesse.services.notifier import notify


def info(msg: str) -> None:
    from jesse.store import store

    store.logs.info.append({'time': jh.now_to_timestamp(), 'message': msg})

    if (jh.is_backtesting() and jh.is_debugging()) or jh.is_collecting_data():
        print('[{}]: {}'.format(jh.timestamp_to_time(jh.now_to_timestamp()), msg))

    if jh.is_live():
        msg = '[INFO | {}] '.format(jh.timestamp_to_time(jh.now_to_timestamp())[:19]) + str(msg)
        import logging
        logging.info(msg)


def error(msg: str) -> None:
    from jesse.store import store

    if jh.is_live() and jh.get_config('env.notifications.events.errors', True):
        notify('ERROR:\n{}'.format(msg))
    if (jh.is_backtesting() and jh.is_debugging()) or jh.is_collecting_data():
        print(jh.color('[{}]: {}'.format(jh.timestamp_to_time(jh.now_to_timestamp()), msg), 'red'))

    store.logs.errors.append({'time': jh.now_to_timestamp(), 'message': msg})

    if jh.is_live() or jh.is_optimizing():
        msg = '[ERROR | {}] '.format(jh.timestamp_to_time(jh.now_to_timestamp())[:19]) + str(msg)
        import logging
        logging.error(msg)
