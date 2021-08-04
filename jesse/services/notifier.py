import requests

import jesse.helpers as jh
from jesse.config import config
from jesse.services.env import ENV_VALUES


def notify(msg: str) -> None:
    """
    sends notifications to "main_telegram_bot" which is supposed to receive messages.
    """
    _telegram(msg)
    _discord(msg)


def notify_urgently(msg: str) -> None:
    """
    sends notifications to "errors_telegram_bot" which we usually do NOT mute
    """
    _telegram_errors_bot(msg)
    _discord_errors(msg)


def _telegram(msg: str) -> None:
    token = ENV_VALUES['GENERAL_TELEGRAM_BOT_TOKEN']
    chat_id: int = ENV_VALUES['GENERAL_TELEGRAM_BOT_CHAT_ID']

    if not token or not config['env']['notifications']['enabled']:
        return

    requests.get(
        f'https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&parse_mode=Markdown&text={msg}'
    )


def _telegram_errors_bot(msg: str) -> None:
    token = ENV_VALUES['ERROR_TELEGRAM_BOT_TOKEN']
    chat_id: int = ENV_VALUES['ERROR_TELEGRAM_BOT_CHAT_ID']

    if not token or not config['env']['notifications']['enabled']:
        return

    requests.get(
        f'https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&parse_mode=Markdown&text={msg}'
    )


def _discord(msg: str) -> None:
    webhook_address = jh.get_config('env.notifications.general_notifier.discord_webhook', '')

    if not webhook_address or not config['env']['notifications']['enabled']:
        return

    requests.post(webhook_address, {'content': msg})


def _discord_errors(msg: str) -> None:
    webhook_address = jh.get_config('env.notifications.error_notifier.discord_webhook', '')

    if not webhook_address or not config['env']['notifications']['enabled']:
        return

    requests.post(webhook_address, {'content': msg})
