import jesse.services.selectors as selectors
from jesse.config import config, reset_config
from jesse.enums import exchanges
from jesse.store import store
from jesse.routes import router


def set_up():
    reset_config()
    config['app']['considering_exchanges'] = [exchanges.SANDBOX]
    config['app']['trading_exchanges'] = [exchanges.SANDBOX]
    config['env']['exchanges'][exchanges.SANDBOX]['balance'] = 2000
    routes = [
        {'exchange': exchanges.SANDBOX, 'symbol': 'BTC-USDT', 'timeframe': '1m', 'strategy': 'TestVanillaStrategy'}
    ]
    router.initiate(routes)


def test_have_correct_exchanges_in_store_after_creating_store():
    set_up()

    e = selectors.get_exchange(exchanges.SANDBOX)
    assert len(store.exchanges.storage) == 1
    assert e.assets['USDT'] == 2000
