import jesse.helpers as jh
from jesse.services import logger
from jesse.info import exchange_info


def save_daily_portfolio_balance(is_initial=False) -> None:
    if is_initial:
        logger.reset()

    from jesse.store import store

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
    try:
        e, = store.exchanges.storage.values()
    except ValueError:
        raise ValueError('Multiple exchange support is not supported at the moment')
    
    if e.type == 'futures':
        # For futures, add wallet balance and sum of all PNLs
        total_balances = e.assets[jh.app_currency()]
        for key, pos in store.positions.storage.items():
            if pos.is_open:
                total_balances += pos.pnl
    else:
        # For spot, just get portfolio_value from any strategy (they all share the same wallet)
        # Get the first strategy we can find
        for key, pos in store.positions.storage.items():
            total_balances = pos.strategy.portfolio_value
            break

    store.app.daily_balance.append(total_balances)

    if not jh.is_livetrading():
        logger.info(f'Saved daily portfolio balance: {round(total_balances, 2)}')


def get_exchange_type(exchange_name: str) -> str:
    """
    a helper for getting the exchange_type for the running session
    """
    # in live trading, exchange type is not configurable, hence we hardcode it
    if jh.is_live():
        return exchange_info[exchange_name]['type']

    # for other trading modes, we can get the exchange type from the config file
    return jh.get_config(f'env.exchanges.{exchange_name}.type')
