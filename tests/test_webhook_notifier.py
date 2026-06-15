from unittest.mock import patch, MagicMock

from jesse.services import notifier


def test_generic_webhook_posts_json_with_timeout():
    with patch.object(notifier.requests, 'post') as post:
        post.return_value = MagicMock(status_code=200)
        notifier._custom_channel_notification({'webhook': 'https://example.com/hook', 'content': 'hello'})
        post.assert_called_once_with('https://example.com/hook', json={'text': 'hello'}, timeout=15)


def test_generic_webhook_falls_back_to_form_on_non_2xx():
    with patch.object(notifier.requests, 'post') as post:
        post.side_effect = [MagicMock(status_code=400, text='bad'), MagicMock(status_code=200)]
        notifier._custom_channel_notification({'webhook': 'https://example.com/hook', 'content': 'hi'})
        assert post.call_count == 2
        _, kwargs = post.call_args_list[1]
        assert kwargs.get('data') == {'text': 'hi'} and kwargs.get('timeout') == 15


def test_slack_url_routes_to_slack_not_generic_post():
    with patch.object(notifier, '_slack') as slack, patch.object(notifier.requests, 'post') as post:
        notifier._custom_channel_notification({'webhook': 'https://hooks.slack.com/services/x', 'content': 'c'})
        slack.assert_called_once_with('c', 'https://hooks.slack.com/services/x')
        post.assert_not_called()


def test_discord_url_routes_to_discord_not_generic_post():
    with patch.object(notifier, '_discord') as disc, patch.object(notifier.requests, 'post') as post:
        notifier._custom_channel_notification({'webhook': 'https://discord.com/api/webhooks/1/x', 'content': 'c'})
        disc.assert_called_once_with('c', 'https://discord.com/api/webhooks/1/x')
        post.assert_not_called()


def test_missing_webhook_logs_and_does_not_post():
    with patch.object(notifier.requests, 'post') as post, patch('jesse.services.logger.error') as log_err:
        notifier._custom_channel_notification({'content': 'c'})  # no webhook key
        post.assert_not_called()
        assert log_err.called


def test_timeout_is_caught_and_logged():
    with patch.object(notifier.requests, 'post', side_effect=notifier.requests.exceptions.Timeout()), \
         patch('jesse.services.logger.error') as log_err:
        notifier._custom_channel_notification({'webhook': 'https://example.com/hook', 'content': 'c'})
        assert log_err.called


def test_non_2xx_on_both_attempts_logs_error():
    with patch.object(notifier.requests, 'post') as post, patch('jesse.services.logger.error') as log_err:
        post.side_effect = [MagicMock(status_code=500, text='err'), MagicMock(status_code=500, text='err')]
        notifier._custom_channel_notification({'webhook': 'https://example.com/hook', 'content': 'c'})
        assert log_err.called


# --- configurable payload key ---

def test_custom_payload_key_is_used():
    with patch.object(notifier.requests, 'post') as post:
        post.return_value = MagicMock(status_code=200)
        notifier._custom_channel_notification({'webhook': 'https://example.com/hook', 'content': 'hi', 'payload_key': 'content'})
        post.assert_called_once_with('https://example.com/hook', json={'content': 'hi'}, timeout=15)


def test_payload_key_falls_back_to_text_when_none():
    with patch.object(notifier.requests, 'post') as post:
        post.return_value = MagicMock(status_code=200)
        notifier._custom_channel_notification({'webhook': 'https://example.com/hook', 'content': 'hi', 'payload_key': None})
        post.assert_called_once_with('https://example.com/hook', json={'text': 'hi'}, timeout=15)


# --- full payload template ---

def test_payload_template_substitutes_message_and_posts_verbatim():
    with patch.object(notifier.requests, 'post') as post:
        post.return_value = MagicMock(status_code=200)
        tmpl = '{"text": "{{message}}", "priority": "high", "tags": ["jesse"]}'
        notifier._custom_channel_notification({'webhook': 'https://example.com/hook', 'content': 'ALERT', 'payload_template': tmpl})
        post.assert_called_once_with(
            'https://example.com/hook',
            json={'text': 'ALERT', 'priority': 'high', 'tags': ['jesse']},
            timeout=15,
        )


def test_payload_template_substitutes_at_any_depth():
    with patch.object(notifier.requests, 'post') as post:
        post.return_value = MagicMock(status_code=200)
        tmpl = '{"attachments": [{"body": {"msg": "{{message}}"}}]}'
        notifier._custom_channel_notification({'webhook': 'https://example.com/hook', 'content': 'deep', 'payload_template': tmpl})
        _, kwargs = post.call_args
        assert kwargs['json'] == {'attachments': [{'body': {'msg': 'deep'}}]}


def test_payload_template_takes_precedence_over_payload_key():
    with patch.object(notifier.requests, 'post') as post:
        post.return_value = MagicMock(status_code=200)
        notifier._custom_channel_notification({
            'webhook': 'https://example.com/hook', 'content': 'x',
            'payload_key': 'content', 'payload_template': '{"msg": "{{message}}"}',
        })
        _, kwargs = post.call_args
        assert kwargs['json'] == {'msg': 'x'}


def test_invalid_payload_template_logs_and_does_not_post():
    with patch.object(notifier.requests, 'post') as post, patch('jesse.services.logger.error') as log_err:
        notifier._custom_channel_notification({'webhook': 'https://example.com/hook', 'content': 'x', 'payload_template': 'not-json{'})
        post.assert_not_called()
        assert log_err.called


def test_template_does_not_form_fallback():
    # a templated POST is explicit JSON — a non-2xx must NOT retry as form-encoded
    with patch.object(notifier.requests, 'post') as post, patch('jesse.services.logger.error') as log_err:
        post.return_value = MagicMock(status_code=500, text='err')
        notifier._custom_channel_notification({'webhook': 'https://example.com/hook', 'content': 'x', 'payload_template': '{"a": "{{message}}"}'})
        assert post.call_count == 1
        assert log_err.called
