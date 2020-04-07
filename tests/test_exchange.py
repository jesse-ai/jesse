from jesse.config import config, reset_config
from jesse.store import store
from jesse.enums import exchanges
import jesse.services.selectors as selectors


def set_up():
    reset_config()
    config['app']['considering_exchanges'] = [exchanges.SANDBOX]
    config['app']['trading_exchanges'] = [exchanges.SANDBOX]
    config['env']['exchanges'][exchanges.SANDBOX]['starting_balance'] = 2000
    store.reset()


def test_increase_balance():
    set_up()

    e = selectors.get_exchange(exchanges.SANDBOX)
    assert e.balance == 2000
    e.increase_balance(None, 100)
    assert e.balance == 2100


def test_decrease_balance():
    set_up()

    e = selectors.get_exchange(exchanges.SANDBOX)
    assert e.balance == 2000
    e.decrease_balance(None, 100)
    assert e.balance == 1900
