import requests
from jesse.services.env import ENV_VALUES
import jesse.helpers as jh
from timeloop import Timeloop
from datetime import timedelta

MSG_QUEUE = []


def start_notifier_loop():
    """
    a constant running loop that runs in a separate thread and
    checks for new messages in the msg_queue. If there are
    any, it sends them by calling _telegram() and _discord()
    """
    tl = Timeloop()

    @tl.job(interval=timedelta(seconds=0.5))
    def handle_time():
        if len(MSG_QUEUE) > 0:
            msg = MSG_QUEUE.pop(0)
            if msg['type'] == 'info':
                if msg['webhook'] is None:
                    _telegram(msg['content'])
                    _discord(msg['content'])
                    _slack(msg['content'])
                else:
                    _custom_channel_notification(msg)

            elif msg['type'] == 'error':
                _telegram_errors(msg['content'])
                _discord(msg['content'], webhook_address=ENV_VALUES['ERROR_DISCORD_WEBHOOK'])
                _slack(msg['content'], webhook_address=ENV_VALUES['ERROR_SLACK_WEBHOOK'] if 'ERROR_SLACK_WEBHOOK' in ENV_VALUES else '')
            else:
                raise ValueError(f'Unknown message type: {msg["type"]}')

    tl.start()


def notify(msg: str, webhook=None) -> None:
    """
    sends notifications to "main_telegram_bot" which is supposed to receive messages.
    """
    msg = _format_msg(msg)

    # Notification drivers don't accept text with more than 2000 characters.
    # So if that's the case limit it to the last 2000 characters.
    if len(msg) > 2000:
        msg = msg[-2000:]

    MSG_QUEUE.append({'type': 'info', 'content': msg, 'webhook': webhook})


def notify_urgently(msg: str) -> None:
    """
    sends notifications to "errors_telegram_bot" which we usually do NOT mute
    """
    msg = _format_msg(msg)

    # Notification drivers don't accept text with more than 2000 characters.
    # So if that's the case limit it to the last 2000 characters.
    if len(msg) > 2000:
        msg = msg[-2000:]

    MSG_QUEUE.append({'type': 'error', 'content': msg})


def _telegram(msg: str) -> None:
    from jesse.services import logger

    token = ENV_VALUES['GENERAL_TELEGRAM_BOT_TOKEN']
    chat_id: int = ENV_VALUES['GENERAL_TELEGRAM_BOT_CHAT_ID']

    if not token or not jh.get_config('env.notifications.enabled'):
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


def _telegram_errors(msg: str) -> None:
    from jesse.services import logger

    token = ENV_VALUES['ERROR_TELEGRAM_BOT_TOKEN']
    chat_id: int = ENV_VALUES['ERROR_TELEGRAM_BOT_CHAT_ID']

    if not token or not jh.get_config('env.notifications.enabled'):
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


def _discord(msg: str, webhook_address=None) -> None:
    from jesse.services import logger

    if webhook_address is None:
        webhook_address = ENV_VALUES['GENERAL_DISCORD_WEBHOOK']

    if not webhook_address or not jh.get_config('env.notifications.enabled'):
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


def _slack(msg: str, webhook_address=None) -> None:
    from jesse.services import logger

    if webhook_address is None:
        webhook_address = ENV_VALUES['GENERAL_SLACK_WEBHOOK'] if 'GENERAL_SLACK_WEBHOOK' in ENV_VALUES else ''

    if not webhook_address or not jh.get_config('env.notifications.enabled'):
        return

    payload = {
        "text": msg
    }

    try:
        response = requests.post(webhook_address, json=payload)
        if response.status_code // 100 != 2:
            err_msg = f'Slack ERROR [{response.status_code}]: {response.text}'
            if response.status_code // 100 == 4:
                err_msg += f'\nParameters: {msg}'
            logger.error(err_msg, send_notification=False)
    except requests.exceptions.ConnectionError:
        logger.error('Slack ERROR: ConnectionError', send_notification=False)


def _custom_channel_notification(msg: dict):
    webhook = msg['webhook']
    # if webhook is an environment variable and not hardcoded
    if webhook in ENV_VALUES:
        webhook = ENV_VALUES[webhook]

    if webhook.startswith('https://hooks.slack.com'):
        # a slack webhook
        _slack(msg['content'], webhook)
    elif webhook.startswith('https://discord.com/api/webhooks'):
        # a discord webhook
        _discord(msg['content'], webhook)
    else:
        raise ValueError(f'Custom Webhook {webhook}. seems to be neither a discord or slack webhook')


def _format_msg(msg: str) -> str:
    # if "_" exists in the message, replace it with "\_"
    msg = msg.replace('_', '\_')
    # # if "*" exists in the message, replace it with "\*"
    # msg = msg.replace('*', '\*')
    # # if "[" exists in the message, replace it with "\["
    # msg = msg.replace('[', '\[')
    # # if "]" exists in the message, replace it with "\}"
    # msg = msg.replace(']', '\]')
    return msg
