import jesse.helpers as jh
from jesse.models.utils import store_daily_balance_into_db
from jesse.services import logger
from jesse.store import store


def save_daily_portfolio_balance() -> None:
    balances = []

    # add exchange balances
    for key, e in store.exchanges.storage.items():
        balances.append(e.assets[jh.app_currency()])

        # # store daily_balance of assets into database
        # if jh.is_livetrading():
        #     for asset_key, asset_value in e.assets.items():
        #         store_daily_balance_into_db({
        #             'id': jh.generate_unique_id(),
        #             'timestamp': jh.now(),
        #             'identifier': jh.get_config('env.identifier', 'main'),
        #             'exchange': e.name,
        #             'asset': asset_key,
        #             'balance': asset_value,
        #         })

    # add open position values
    for key, pos in store.positions.storage.items():
        if pos.is_open:
            balances.append(pos.pnl)

    total = sum(balances)
    store.app.daily_balance.append(total)

    # TEMP: disable storing in database for now
    if not jh.is_livetrading():
        logger.info(f'Saved daily portfolio balance: {round(total, 2)}')
