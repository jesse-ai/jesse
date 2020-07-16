from math import log10

import arrow
import click
import numpy as np

import jesse.helpers as jh
import jesse.services.required_candles as required_candles
from jesse import exceptions
from jesse.config import config
from jesse.models import Candle
from jesse.modes.backtest_mode import simulator
from jesse.routes import router
from jesse.services import statistics as stats
from jesse.services.cache import cache
from jesse.store import store
from .Genetics import Genetics


class Optimizer(Genetics):
    def __init__(self, training_candles, testing_candles):
        if len(router.routes) != 1:
            raise NotImplementedError('optimize_mode mode only supports one route at the moment')

        self.strategy_name = router.routes[0].strategy_name
        self.exchange = router.routes[0].exchange
        self.symbol = router.routes[0].symbol
        self.timeframe = router.routes[0].timeframe
        StrategyClass = jh.get_strategy_class(self.strategy_name)
        self.strategy_hp = StrategyClass.hyper_parameters()
        solution_len = len(self.strategy_hp)

        if solution_len == 0:
            raise exceptions.InvalidStrategy('Targeted strategy does not implement a valid hyper_parameters() method.')

        super().__init__(
            iterations=2000 * solution_len,
            population_size=solution_len * 100,
            solution_len=solution_len,
            options={
                'strategy_name': self.strategy_name,
                'exchange': self.exchange,
                'symbol': self.symbol,
                'timeframe': self.timeframe
            }
        )

        self.training_candles = training_candles
        self.testing_candles = testing_candles

        key = jh.key(self.exchange, self.symbol)

        # training
        self.required_initial_training_candles = required_candles.load_required_candles(
            self.exchange,
            self.symbol,
            # SOMEHOW there is T00:00:00.000Z appended to the time. Therefore the split
            jh.timestamp_to_time(self.training_candles[key]['candles'][0][0]).split('T')[0],
            jh.timestamp_to_time(self.training_candles[key]['candles'][-1][0]).split('T')[0]
        )
        # testing
        self.required_initial_testing_candles = required_candles.load_required_candles(
            self.exchange,
            self.symbol,
            # SOMEHOW there is T00:00:00.000Z appended to the time. Therefore the split
            jh.timestamp_to_time(self.testing_candles[key]['candles'][0][0]).split('T')[0],
            jh.timestamp_to_time(self.testing_candles[key]['candles'][-1][0]).split('T')[0]
        )

    def fitness(self, dna) -> tuple:
        hp = jh.dna_to_hp(self.strategy_hp, dna)

        # init candle store
        store.candles.init_storage(5000)
        # inject required TRAINING candles to the candle store
        required_candles.inject_required_candles_to_store(
            self.required_initial_training_candles,
            self.exchange,
            self.symbol
        )
        # run backtest simulation
        simulator(self.training_candles, hp)

        log = ''

        # TODO: some of these have to be dynamic based on how many days it's trading for like for example "total"
        # I'm guessing we should accept "optimal" total from command line
        if store.completed_trades.count > 5:
            training_data = stats.trades(store.completed_trades.trades, store.app.daily_balance)
            optimal_expected_total = 100
            total = jh.normalize(training_data['total'], 0, 200)
            total_effect_rate = log10(training_data['total']) / log10(optimal_expected_total)
            win_rate = training_data['win_rate']

            # log for debugging/monitoring
            log = 'win_rate:[{}-{}], total:[{}-{}], PNL%:[{}], TER:[{}]'.format(
                round(win_rate, 2), round(training_data['win_rate'], 2),
                round(total, 2), training_data['total'],
                round(training_data['net_profit_percentage'], 2),
                round(total_effect_rate, 3)
            )

            # the fitness score - I tried to include the sharpe, sortino and calmar ratio to the fitness score.
            score = win_rate * total_effect_rate * ((training_data['sharpe_ratio'] + training_data['sortino_ratio'] +  training_data['calmar_ratio']) / 3)

            # perform backtest with testing data. this is using data
            # model hasn't trained for. if it works well, there is
            # high change it will do good with future data too.
            store.reset()
            store.candles.init_storage(5000)
            # inject required TESTING candles to the candle store
            required_candles.inject_required_candles_to_store(
                self.required_initial_testing_candles,
                self.exchange,
                self.symbol
            )
            # run backtest simulation
            simulator(self.testing_candles, hp)
            testing_data = stats.trades(store.completed_trades.trades, store.app.daily_balance)

            # log for debugging/monitoring
            log += ' | '
            log += 'win_rate:[{}], total:[{}], PNL%:[{}]'.format(
                round(testing_data['win_rate'], 2),
                testing_data['total'],
                round(testing_data['net_profit_percentage'], 2),
            )
            if testing_data['net_profit_percentage'] > 0 and training_data['net_profit_percentage'] > 0:
                log = jh.style(log, 'bold')
        else:
            score = 0.0001

        # reset store
        store.reset()

        return score, log


def optimize_mode(start_date: str, finish_date: str):
    # clear the screen
    click.clear()
    print('loading candles...')

    # load historical candles and divide them into training
    # and testing candles (15% for test, 85% for training)
    training_candles, testing_candles = get_training_and_testing_candles(start_date, finish_date)

    # clear the screen
    click.clear()

    optimizer = Optimizer(training_candles, testing_candles)

    optimizer.run()

    # TODO: store hyper parameters into each strategies folder per each Exchange-symbol-timeframe


def get_training_and_testing_candles(start_date_str: str, finish_date_str: str):
    start_date = jh.arrow_to_timestamp(arrow.get(start_date_str, 'YYYY-MM-DD'))
    finish_date = jh.arrow_to_timestamp(arrow.get(finish_date_str, 'YYYY-MM-DD')) - 60000

    # validate
    if start_date == finish_date:
        raise ValueError('start_date and finish_date cannot be the same.')
    if start_date > finish_date:
        raise ValueError('start_date cannot be bigger than finish_date.')
    if finish_date > arrow.utcnow().timestamp * 1000:
        raise ValueError('Can\'t optimize the future!')

    # Load candles (first try cache, then database)
    from jesse.modes.backtest_mode import load_candles
    candles = load_candles(start_date_str, finish_date_str)

    # divide into training(85%) and testing(15%) sets
    training_candles = {}
    testing_candles = {}
    days_diff = jh.date_diff_in_days(jh.get_arrow(start_date), jh.get_arrow(finish_date))
    divider_index = int(days_diff * 0.85) * 1440
    for key in candles:
        training_candles[key] = {
            'exchange': candles[key]['exchange'],
            'symbol': candles[key]['symbol'],
            'candles': candles[key]['candles'][0:divider_index],
        }

        testing_candles[key] = {
            'exchange': candles[key]['exchange'],
            'symbol': candles[key]['symbol'],
            'candles': candles[key]['candles'][divider_index:],
        }

    return training_candles, testing_candles
