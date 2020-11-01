from jesse.store import store
from jesse import helpers
from jesse.services import logger


def save_daily_portfolio_balance():
    balances = []

    # add exchange balances
    for key, e in store.exchanges.storage.items():
        balances.append(e.assets[helpers.app_currency()])

    # add open position values
    for key, pos in store.positions.storage.items():
        if pos.is_open:
            balances.append(pos.pnl)

    total = sum(balances)
    store.app.daily_balance.append(total)
    logger.info('Saved daily portfolio balance: {}'.format(round(total, 2)))
