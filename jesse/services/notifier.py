import json

import requests
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
    from jesse.store import store
    from jesse.services.transformers import get_notification_api_key

    tl = Timeloop()
    @tl.job(interval=timedelta(seconds=0.5))
    def handle_time():
        # Guard the whole loop body: a single bad message or transient error must
        # never kill the notifier thread (timeloop does not restart a dead job).
        try:
            if len(MSG_QUEUE) > 0:
                msg = MSG_QUEUE.pop(0)

                notification_keys = get_notification_api_key(store.app.notifications_api_key, protect_sensitive_data=False) if store.app.notifications_api_key else None

                if msg['type'] == 'info':
                    if msg['webhook'] is None and notification_keys:
                        if notification_keys['driver'] == 'telegram':
                            _telegram(msg['content'], notification_keys['bot_token'], notification_keys['chat_id'])
                        elif notification_keys['driver'] == 'discord':
                            _discord(msg['content'], webhook_address=notification_keys['webhook'])
                        elif notification_keys['driver'] == 'slack':
                            _slack(msg['content'], webhook_address=notification_keys['webhook'])
                        elif notification_keys['driver'] == 'webhook':
                            _custom_channel_notification({
                                'content': msg['content'],
                                'webhook': notification_keys['webhook'],
                                'payload_key': notification_keys.get('payload_key'),
                                'payload_template': notification_keys.get('payload_template'),
                            })
                    elif notification_keys:
                        _custom_channel_notification(msg)

                # elif msg['type'] == 'error' and error_notifications:
                #     if error_notifications['driver'] == 'telegram':
                #         _telegram_errors(msg['content'], error_notifications['bot_token'], error_notifications['chat_id'])
                #     elif error_notifications['driver'] == 'discord':
                #         _discord(msg['content'], webhook_address=error_notifications['webhook'])
                #     elif error_notifications['driver'] == 'slack':
                #         _slack(msg['content'], webhook_address=error_notifications['webhook'])
                else:
                    raise ValueError(f'Unknown message type: {msg["type"]}')
        except Exception as e:
            from jesse.services import logger
            logger.error(f'Notifier loop error (non-fatal): {type(e).__name__}: {e}', send_notification=False)

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


def _telegram(msg: str, token: str, chat_id: str) -> None:
    from jesse.services import logger

    if not token or not jh.get_config('env.notifications.enabled'):
        return

    try:
        response = requests.get(
            f'https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&parse_mode=Markdown&text={msg}',
            timeout=15
        )
        if response.status_code // 100 != 2:
            err_msg = f'Telegram ERROR [{response.status_code}]: {response.text}'
            if response.status_code // 100 == 4:
                err_msg += f'\nParameters: {msg}'
            logger.error(err_msg, send_notification=False)
    except requests.exceptions.RequestException as e:
        logger.error(f'Telegram ERROR (non-fatal): {type(e).__name__}', send_notification=False)


def _discord(msg: str, webhook_address=None) -> None:
    from jesse.services import logger

    if not jh.get_config('env.notifications.enabled'):
        return

    try:
        response = requests.post(webhook_address, {'content': msg}, timeout=15)
        if response.status_code // 100 != 2:
            err_msg = f'Discord ERROR [{response.status_code}]: {response.text}'
            if response.status_code // 100 == 4:
                err_msg += f'\nParameters: {msg}'
            logger.error(err_msg, send_notification=False)
    except requests.exceptions.RequestException as e:
        logger.error(f'Discord ERROR (non-fatal): {type(e).__name__}', send_notification=False)


def _slack(msg: str, webhook_address) -> None:
    from jesse.services import logger

    if not jh.get_config('env.notifications.enabled'):
        return

    payload = {
        "text": msg
    }

    try:
        response = requests.post(webhook_address, json=payload, timeout=15)
        if response.status_code // 100 != 2:
            err_msg = f'Slack ERROR [{response.status_code}]: {response.text}'
            if response.status_code // 100 == 4:
                err_msg += f'\nParameters: {msg}'
            logger.error(err_msg, send_notification=False)
    except requests.exceptions.RequestException as e:
        logger.error(f'Slack ERROR (non-fatal): {type(e).__name__}', send_notification=False)


def _custom_channel_notification(msg: dict):
    from jesse.services import logger

    webhook = msg.get('webhook')
    if not webhook:
        logger.error('Custom webhook notification called without a webhook URL', send_notification=False)
        return

    content = msg.get('content', '')

    # Slack and Discord expect their own payload shapes — route to the dedicated senders.
    if webhook.startswith('https://hooks.slack.com'):
        _slack(content, webhook)
        return
    if webhook.startswith('https://discord.com/api/webhooks'):
        _discord(content, webhook)
        return

    # Generic webhook. The request body is fully configurable so it can satisfy whatever
    # the target service expects:
    #   - payload_template: the user's own JSON object (any shape, extra fields, nesting),
    #     with a "{{message}}" placeholder substituted with the notification text. POSTed
    #     verbatim as JSON.
    #   - payload_key: simpler shortcut when only the field name differs — sends
    #     {payload_key: content}. Defaults to 'text' (widely accepted, e.g. MS Teams/Slack).
    # payload_template takes precedence when both are set.
    template = msg.get('payload_template')
    if template:
        try:
            parsed = json.loads(template) if isinstance(template, str) else template
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f'Webhook ERROR: invalid payload template ({e})', send_notification=False)
            return
        _post_webhook(webhook, _apply_payload_template(parsed, content))
        return

    payload_key = msg.get('payload_key') or 'text'
    _post_webhook(webhook, {payload_key: content}, form_fallback={payload_key: content})


def _apply_payload_template(obj, content: str):
    """Recursively substitute the "{{message}}" placeholder with the notification content."""
    if isinstance(obj, str):
        return obj.replace('{{message}}', content)
    if isinstance(obj, list):
        return [_apply_payload_template(item, content) for item in obj]
    if isinstance(obj, dict):
        return {key: _apply_payload_template(value, content) for key, value in obj.items()}
    return obj


def _post_webhook(webhook: str, json_payload, form_fallback=None) -> None:
    """POST a payload to a generic webhook with a timeout; retry form-encoded if given.
    Any failure (non-2xx, connection error, timeout) is logged without raising, so the
    notifier loop is never stalled or killed."""
    from jesse.services import logger
    try:
        response = requests.post(webhook, json=json_payload, timeout=15)
        if response.status_code // 100 != 2 and form_fallback is not None:
            response = requests.post(webhook, data=form_fallback, timeout=15)
        if response.status_code // 100 != 2:
            logger.error(f'Webhook ERROR [{response.status_code}]: {response.text}', send_notification=False)
    except requests.exceptions.ConnectionError:
        logger.error('Webhook ERROR: ConnectionError', send_notification=False)
    except requests.exceptions.Timeout:
        logger.error('Webhook ERROR: timed out', send_notification=False)
    except Exception as e:
        logger.error(f'Webhook ERROR: {e}', send_notification=False)


def _format_msg(msg: str) -> str:
    # if "_" exists in the message, replace it with "\_"
    msg = msg.replace('_', r'\_')
    # # if "*" exists in the message, replace it with "\*"
    # msg = msg.replace('*', '\*')
    # # if "[" exists in the message, replace it with "\["
    # msg = msg.replace('[', '\[')
    # # if "]" exists in the message, replace it with "\}"
    # msg = msg.replace(']', '\]')
    return msg
