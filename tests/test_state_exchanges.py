import jesse.services.selectors as selectors
from jesse.config import config, reset_config
from jesse.enums import Exchanges
from jesse.store import store
from jesse.routes import router


def set_up():
    reset_config()
    config['app']['considering_exchanges'] = [Exchanges.SANDBOX]
    config['app']['trading_exchanges'] = [Exchanges.SANDBOX]
    config['env']['exchanges'][Exchanges.SANDBOX]['balance'] = 2000
    routes = [
        {'exchange': Exchanges.SANDBOX, 'symbol': 'BTC-USDT', 'timeframe': '1m', 'strategy': 'TestVanillaStrategy'}
    ]
    router.initiate(routes)


def test_have_correct_exchanges_in_store_after_creating_store():
    set_up()

    e = selectors.get_exchange(Exchanges.SANDBOX)
    assert len(store.exchanges.storage) == 1
    assert e.assets['USDT'] == 2000
