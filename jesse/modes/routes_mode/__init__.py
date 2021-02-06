from typing import List, Any

import jesse.helpers as jh
from jesse.routes import router
from jesse.services import table


def run(dna: bool = False) -> None:
    # trading routes
    arr = []
    if not dna:
        print(
            jh.color('{}{}{}'.format('#' * 25, ' Trading Routes ', '#' * 25), 'blue')
        )
        arr.append(('exchange', 'symbol', 'timeframe', 'strategy name', 'DNA'))
    else:
        print(
            jh.color('Translated DNAs into hyper-parameters:', 'blue')
        )

    translated_DNAs_count = 0
    for i, r in enumerate(router.routes):
        if dna and r.dna:
            translated_DNAs_count += 1
            StrategyClass = jh.get_strategy_class(r.strategy_name)
            hyperparameters = jh.dna_to_hp(StrategyClass.hyperparameters(None), r.dna)
            table.key_value(hyperparameters.items(), r.strategy_name, uppercase_title=False)
            print('\n')
        else:
            arr.append([r.exchange, r.symbol, r.timeframe, r.strategy_name, r.dna])
    if not dna:
        table.multi_value(arr)
        print('\n')
    else:
        if not translated_DNAs_count:
            print('No DNA string found.')

    # extra_candles
    if not dna:
        print(
            jh.color('{}{}{}'.format('#' * 25, ' Extra Candles ', '#' * 25), 'blue')
        )
        arr = [('exchange', 'symbol', 'timeframe')]

        for i, r in enumerate(router.extra_candles):
            arr.append([r[0], r[1], r[2]])

        table.multi_value(arr)
        print('\n')
