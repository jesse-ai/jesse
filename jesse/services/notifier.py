import requests
from jesse.config import config
from jesse.services.env import ENV_VALUES
from jesse.services import logger


def notify(msg: str) -> None:
    """
    sends notifications to "main_telegram_bot" which is supposed to receive messages.
    """
    msg = _format_msg(msg)

    # Notification drivers don't accept text with more than 2000 characters.
    # So if that's the case limit it to the last 2000 characters.
    if len(msg) > 2000:
        msg = msg[-2000:]

    _telegram(msg)
    _discord(msg)


def notify_urgently(msg: str) -> None:
    """
    sends notifications to "errors_telegram_bot" which we usually do NOT mute
    """
    msg = _format_msg(msg)

    # Notification drivers don't accept text with more than 2000 characters.
    # So if that's the case limit it to the last 2000 characters.
    if len(msg) > 2000:
        msg = msg[-2000:]

    _telegram_errors_bot(msg)
    _discord_errors(msg)


def _telegram(msg: str) -> None:
    token = ENV_VALUES['GENERAL_TELEGRAM_BOT_TOKEN']
    chat_id: int = ENV_VALUES['GENERAL_TELEGRAM_BOT_CHAT_ID']

    if not token or not config['env']['notifications']['enabled']:
        return

    try:
        response = requests.get(
            f'https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&parse_mode=Markdown&text={msg}'
        )
        if response.status_code // 100 != 2:
            err_msg = f'Telegram ERROR [{response.status_code}]: {response.text}'
            if response.status_code // 100 == 4:
                err_msg += f'\nParameters: {msg}'
            logger.error(err_msg, send_notification=False)
    except requests.exceptions.ConnectionError:
        logger.error('Telegram ERROR: ConnectionError', send_notification=False)


def _telegram_errors_bot(msg: str) -> None:
    token = ENV_VALUES['ERROR_TELEGRAM_BOT_TOKEN']
    chat_id: int = ENV_VALUES['ERROR_TELEGRAM_BOT_CHAT_ID']

    if not token or not config['env']['notifications']['enabled']:
        return

    try:
        response = requests.get(
            f'https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&parse_mode=Markdown&text={msg}'
        )
        if response.status_code // 100 != 2:
            err_msg = f'Telegram ERROR [{response.status_code}]: {response.text}'
            if response.status_code // 100 == 4:
                err_msg += f'\nParameters: {msg}'
            logger.error(err_msg, send_notification=False)
    except requests.exceptions.ConnectionError:
        logger.error('Telegram ERROR: ConnectionError', send_notification=False)


def _discord(msg: str) -> None:
    webhook_address = ENV_VALUES['GENERAL_DISCORD_WEBHOOK']

    if not webhook_address or not config['env']['notifications']['enabled']:
        return

    try:
        response = requests.post(webhook_address, {'content': msg})
        if response.status_code // 100 != 2:
            err_msg = f'Discord ERROR [{response.status_code}]: {response.text}'
            if response.status_code // 100 == 4:
                err_msg += f'\nParameters: {msg}'
            logger.error(err_msg, send_notification=False)
    except requests.exceptions.ConnectionError:
        logger.error('Discord ERROR: ConnectionError', send_notification=False)


def _discord_errors(msg: str) -> None:
    webhook_address = ENV_VALUES['ERROR_DISCORD_WEBHOOK']

    if not webhook_address or not config['env']['notifications']['enabled']:
        return

    try:
        response = requests.post(webhook_address, {'content': msg})
        if response.status_code // 100 != 2:
            err_msg = f'Discord ERROR [{response.status_code}]: {response.text}'
            if response.status_code // 100 == 4:
                err_msg += f'\nParameters: {msg}'
            logger.error(err_msg, send_notification=False)
    except requests.exceptions.ConnectionError:
        logger.error('Discord ERROR: ConnectionError', send_notification=False)


def _format_msg(msg: str) -> str:
    # if "_" exists in the message, replace it with "\_"
    msg = msg.replace('_', '\_')
    # if "*" exists in the message, replace it with "\*"
    msg = msg.replace('*', '\*')
    # if "[" exists in the message, replace it with "\["
    msg = msg.replace('[', '\[')
    # if "]" exists in the message, replace it with "\}"
    msg = msg.replace(']', '\]')
    return msg
