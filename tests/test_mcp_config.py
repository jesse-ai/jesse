import json

import jesse.mcp.tools.services.config as config_service


class _SuccessfulResponse:
    status_code = 200


def test_update_config_unwraps_get_config_envelope(monkeypatch):
    captured_request = {}

    def fake_post(url, **kwargs):
        captured_request['url'] = url
        captured_request.update(kwargs)
        return _SuccessfulResponse()

    monkeypatch.setattr(config_service.mcp_config, 'JESSE_API_URL', 'http://jesse.test')
    monkeypatch.setattr(config_service.mcp_config, 'JESSE_PASSWORD', 'test-password')
    monkeypatch.setattr('requests.post', fake_post)

    result = config_service.update_config_service(json.dumps({
        'data': {
            'backtest': {
                'exchanges': {
                    'Binance Perpetual Futures': {'fee': 0}
                }
            }
        }
    }))

    assert result == {
        'status': 'success',
        'message': 'Configuration updated successfully'
    }
    assert captured_request['url'] == 'http://jesse.test/config/update'
    assert captured_request['json'] == {
        'current_config': {
            'backtest': {
                'exchanges': {
                    'Binance Perpetual Futures': {'fee': 0}
                }
            }
        }
    }


def test_update_config_preserves_direct_partial_payload(monkeypatch):
    captured_request = {}

    def fake_post(_url, **kwargs):
        captured_request.update(kwargs)
        return _SuccessfulResponse()

    monkeypatch.setattr(config_service.mcp_config, 'JESSE_PASSWORD', 'test-password')
    monkeypatch.setattr('requests.post', fake_post)

    result = config_service.update_config_service(json.dumps({
        'backtest': {'warm_up_candles': 300}
    }))

    assert result['status'] == 'success'
    assert captured_request['json'] == {
        'current_config': {
            'backtest': {'warm_up_candles': 300}
        }
    }
