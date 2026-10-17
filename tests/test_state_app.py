from types import SimpleNamespace

import pytest

import jesse.store.state_app as state_app
from jesse.services import order_service
from jesse.store import store
from jesse.store.state_app import AppState


def stored_keys(monkeypatch, keys):
    """Stand in for the exchange API keys saved in the database."""
    class FakeExchangeApiKeys:
        id = 'id'
        exchange_name = 'exchange_name'

        @staticmethod
        def get_or_none(_):
            return keys[0]

        @staticmethod
        def select():
            return SimpleNamespace(where=lambda _: SimpleNamespace(
                count=lambda: sum(k.exchange_name == keys[0].exchange_name for k in keys)
            ))

    monkeypatch.setattr(state_app, 'ExchangeApiKeys', FakeExchangeApiKeys)


def key(name, exchange='Lighter Perpetual'):
    return SimpleNamespace(name=name, exchange_name=exchange)


def test_exchange_label_names_the_account_when_the_exchange_has_several_keys(monkeypatch):
    stored_keys(monkeypatch, [key('Main'), key('Sub 2')])
    app = AppState()

    app.set_exchange_api_key('key-id')

    assert app.exchange_label('Lighter Perpetual') == 'Lighter Perpetual | Main'


def test_exchange_label_is_just_the_exchange_when_its_only_key_is_used(monkeypatch):
    stored_keys(monkeypatch, [key('Main'), key('Other exchange', exchange='Bybit USDT Perpetual')])
    app = AppState()

    app.set_exchange_api_key('key-id')

    assert app.exchange_label('Lighter Perpetual') == 'Lighter Perpetual'


def test_exchange_label_is_just_the_exchange_without_an_api_key():
    assert AppState().exchange_label('Lighter Perpetual') == 'Lighter Perpetual'


@pytest.mark.parametrize('account, expected', [
    (None, '📤 Order submitted | ETH-USD | Lighter Perpetual | BUY STOP | Qty: 4.9068 | Price: 2419.42'),
    ('Main', '📤 Order submitted | ETH-USD | Lighter Perpetual | Main | BUY STOP | Qty: 4.9068 | Price: 2419.42'),
])
def test_order_message_names_a_shared_exchange_account(monkeypatch, account, expected):
    monkeypatch.setattr(store, 'app', AppState())
    store.app.shared_exchange_account_name = account
    order = SimpleNamespace(
        symbol='ETH-USD', exchange='Lighter Perpetual', side='buy', type='STOP', qty=4.9068, price=2419.42,
    )

    assert order_service._order_message(order, '📤 Order submitted') == expected
