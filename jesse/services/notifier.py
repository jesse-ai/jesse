import requests

import jesse.helpers as jh
from jesse.config import config


def notify(msg):
    """

    :param msg:
    """
    _telegram(msg)


def _telegram(msg):
    token = jh.get_config('env.notifications.telegram_bot_token', '')
    chat_IDs: list = jh.get_config('env.notifications.telegram_chat_IDs', [])

    if not token or not len(chat_IDs) or not config['env']['notifications']['enable_notifications']:
        return

    for id in chat_IDs:
        requests.get(
            'https://api.telegram.org/bot{}/sendMessage?chat_id={}&parse_mode=Markdown&text={}'.format(
                token, id, msg
            )
        )
