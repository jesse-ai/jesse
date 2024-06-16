import requests
import jesse.helpers as jh
from timeloop import Timeloop
from datetime import timedelta
from jesse import store
from jesse.services.transformers import get_notification_api_key

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

            general_notifications = get_notification_api_key(store.state_app.ExchangeApiKeys.general_notifications, protect_sensitive_data=False)
            error_notifications = get_notification_api_key(store.state_app.ExchangeApiKeys.error_notifications, protect_sensitive_data=False)

            if msg['type'] == 'info':
                if msg['webhook'] is None:
                    if general_notifications['driver'] == 'telegram':
                        _telegram(msg['content'], general_notifications['bot_token'], general_notifications['chat_id'])
                    elif general_notifications['driver'] == 'discord':
                        _discord(msg['content'], webhook_address=general_notifications['webhook'])
                    elif general_notifications['driver'] == 'slack':
                        _slack(msg['content'], webhook_address=general_notifications['webhook'])
                else:
                    _custom_channel_notification(msg)

            elif msg['type'] == 'error':
                if error_notifications['driver'] == 'telegram':
                    _telegram_errors(msg['content'], error_notifications['bot_token'], error_notifications['chat_id'])
                elif error_notifications['driver'] == 'discord':
                    _discord(msg['content'], webhook_address=error_notifications['webhook'])
                elif error_notifications['driver'] == 'slack':
                    _slack(msg['content'], webhook_address=error_notifications['webhook'])
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


def _telegram(msg: str, token: str, chat_id: str) -> None:
    from jesse.services import logger

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


def _telegram_errors(msg: str, token: str, chat_id: str) -> None:
    from jesse.services import logger

    if not jh.get_config('env.notifications.enabled'):
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

    if not jh.get_config('env.notifications.enabled'):
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


def _slack(msg: str, webhook_address) -> None:
    from jesse.services import logger

    if not jh.get_config('env.notifications.enabled'):
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
