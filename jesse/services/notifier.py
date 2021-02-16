import requests

import jesse.helpers as jh
from jesse.config import config


def notify(msg: str) -> None:
    """
    sends notifications to "main_telegram_bot" which is supposed to receive messages.
    """
    _telegram(msg)


def notify_urgently(msg: str) -> None:
    """
    sends notifications to "errors_telegram_bot" which we usually do NOT mute
    """
    _telegram_errors_bot(msg)


def _telegram(msg: str) -> None:
    token = jh.get_config('env.notifications.main_telegram_bot_token', '')
    chat_IDs: list = jh.get_config('env.notifications.main_telegram_chat_IDs', [])

    if not token or not len(chat_IDs) or not config['env']['notifications']['enable_notifications']:
        return

    for id in chat_IDs:
        requests.get(
            'https://api.telegram.org/bot{}/sendMessage?chat_id={}&parse_mode=Markdown&text={}'.format(
                token, id, msg
            )
        )


def _telegram_errors_bot(msg: str) -> None:
    token = jh.get_config('env.notifications.errors_telegram_bot_token', '')
    chat_IDs: list = jh.get_config('env.notifications.errors_telegram_chat_IDs', [])

    if not token or not len(chat_IDs) or not config['env']['notifications']['enable_notifications']:
        return

    for id in chat_IDs:
        requests.get(
            'https://api.telegram.org/bot{}/sendMessage?chat_id={}&parse_mode=Markdown&text={}'.format(
                token, id, msg
            )
        )
