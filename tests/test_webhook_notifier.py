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
