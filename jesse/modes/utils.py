import jesse.helpers as jh
# from jesse.models.utils import store_daily_balance_into_db
from jesse.services import logger
from jesse.store import store


def save_daily_portfolio_balance() -> None:
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
    total_balances = 0
    # select the first item in store.exchanges.storage.items()
    e, = store.exchanges.storage.values()
    if e.type == 'futures':
        try:
            total_balances += e.assets[jh.app_currency()]
        except KeyError:
            raise ValueError('Invalid quote trading pair. Check your trading route\'s symbol')

    for key, pos in store.positions.storage.items():
        if pos.exchange_type == 'futures' and pos.is_open:
            total_balances += pos.pnl
        elif pos.exchange_type == 'spot':
            total_balances += pos.strategy.portfolio_value

    store.app.daily_balance.append(total_balances)

    # TEMP: disable storing in database for now
    if not jh.is_livetrading():
        logger.info(f'Saved daily portfolio balance: {round(total_balances, 2)}')
