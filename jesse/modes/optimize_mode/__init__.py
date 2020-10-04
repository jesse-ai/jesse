from math import log10
from multiprocessing import cpu_count

import arrow
import click

import jesse.helpers as jh
import jesse.services.required_candles as required_candles
from jesse import exceptions
from jesse.config import config
from jesse.modes.backtest_mode import simulator
from jesse.routes import router
from jesse.services import statistics as stats
from jesse.services.validators import validate_routes
from jesse.store import store
from .Genetics import Genetics


class Optimizer(Genetics):
    def __init__(self, training_candles, testing_candles, optimal_total, cpu_cores):
        if len(router.routes) != 1:
            raise NotImplementedError('optimize_mode mode only supports one route at the moment')

        self.strategy_name = router.routes[0].strategy_name
        self.optimal_total = optimal_total
        self.exchange = router.routes[0].exchange
        self.symbol = router.routes[0].symbol
        self.timeframe = router.routes[0].timeframe
        StrategyClass = jh.get_strategy_class(self.strategy_name)
        self.strategy_hp = StrategyClass.hyperparameters(None)
        solution_len = len(self.strategy_hp)

        if solution_len == 0:
            raise exceptions.InvalidStrategy('Targeted strategy does not implement a valid hyperparameters() method.')

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

        if cpu_cores > cpu_count():
            raise ValueError('Entered cpu cores number is more than available on this machine which is {}'.format(
                cpu_count()
            ))
        elif cpu_cores == 0:
            self.cpu_cores = cpu_count()
        else:
            self.cpu_cores = cpu_cores

        self.training_candles = training_candles
        self.testing_candles = testing_candles

        key = jh.key(self.exchange, self.symbol)
        training_candles_start_date = jh.timestamp_to_time(self.training_candles[key]['candles'][0][0]).split('T')[0]
        training_candles_finish_date = jh.timestamp_to_time(self.training_candles[key]['candles'][-1][0]).split('T')[0]
        testing_candles_start_date = jh.timestamp_to_time(self.testing_candles[key]['candles'][0][0]).split('T')[0]
        testing_candles_finish_date = jh.timestamp_to_time(self.testing_candles[key]['candles'][-1][0]).split('T')[0]

        self.training_initial_candles = []
        self.testing_initial_candles = []

        for c in config['app']['considering_candles']:
            self.training_initial_candles.append(
                required_candles.load_required_candles(c[0], c[1], training_candles_start_date,
                                                       training_candles_finish_date))
            self.testing_initial_candles.append(
                required_candles.load_required_candles(c[0], c[1], testing_candles_start_date,
                                                       testing_candles_finish_date))

    def fitness(self, dna) -> tuple:
        hp = jh.dna_to_hp(self.strategy_hp, dna)

        # init candle store
        store.candles.init_storage(5000)
        # inject required TRAINING candles to the candle store

        for num, c in enumerate(config['app']['considering_candles']):
            required_candles.inject_required_candles_to_store(
                self.training_initial_candles[num],
                c[0],
                c[1]
            )

        # run backtest simulation
        simulator(self.training_candles, hp)

        log = ''

        # TODO: some of these have to be dynamic based on how many days it's trading for like for example "total"
        # I'm guessing we should accept "optimal" total from command line
        if store.completed_trades.count > 5:
            training_data = stats.trades(store.completed_trades.trades, store.app.daily_balance)
            total_effect_rate = log10(training_data['total']) / log10(self.optimal_total)
            if total_effect_rate > 1:
                total_effect_rate = 1
            win_rate = training_data['win_rate']

            ratio_config = jh.get_config('env.optimization.ratio', 'sharpe')
            if ratio_config == 'sharpe':
                ratio = training_data['sharpe_ratio']
            elif ratio_config == 'calmar':
                ratio = training_data['calmar_ratio']
            elif ratio_config == 'sortiono':
                ratio = training_data['sortino_ratio']
            elif ratio_config == 'omega':
                ratio = training_data['omega_ratio']
            else:
                raise ValueError(
                    'The entered ratio configuration `{}` for the optimization is unknown. Choose between sharpe, calmar, sortino and omega.'.format(
                        ratio_config))

            if ratio < 0:
                score = 0.0001
                # reset store
                store.reset()
                return score, log

            ratio_normalized = jh.normalize(ratio, -.5, 4)

                # log for debugging/monitoring
            log = 'win-rate: {}%, total: {}, PNL: {}%'.format(
                int(win_rate * 100),
                training_data['total'],
                round(training_data['net_profit_percentage'], 2),
            )

            score = total_effect_rate * ratio_normalized

            # perform backtest with testing data. this is using data
            # model hasn't trained for. if it works well, there is
            # high change it will do good with future data too.
            store.reset()
            store.candles.init_storage(5000)
            # inject required TESTING candles to the candle store

            for num, c in enumerate(config['app']['considering_candles']):
                required_candles.inject_required_candles_to_store(
                    self.testing_initial_candles[num],
                    c[0],
                    c[1]
                )

            # run backtest simulation
            simulator(self.testing_candles, hp)
            testing_data = stats.trades(store.completed_trades.trades, store.app.daily_balance)

            # log for debugging/monitoring
            log += ' || '
            if store.completed_trades.count > 0:
                log += 'win-rate: {}%, total: {}, PNL: {}%'.format(
                    int(testing_data['win_rate'] * 100),
                    testing_data['total'],
                    round(testing_data['net_profit_percentage'], 2),
                )
                if testing_data['net_profit_percentage'] > 0 and training_data['net_profit_percentage'] > 0:
                    log = jh.style(log, 'bold')
            else:
                log += 'win-rate: -, total: -, PNL%: -'
        else:
            score = 0.0001

        # reset store
        store.reset()

        return score, log


def optimize_mode(start_date: str, finish_date: str, optimal_total: int, cpu_cores: int):
    # clear the screen
    click.clear()
    print('loading candles...')

    # validate routes
    validate_routes(router)

    # load historical candles and divide them into training
    # and testing candles (15% for test, 85% for training)
    training_candles, testing_candles = get_training_and_testing_candles(start_date, finish_date)

    # clear the screen
    click.clear()

    optimizer = Optimizer(training_candles, testing_candles, optimal_total, cpu_cores)

    optimizer.run()

    # TODO: store hyper parameters into each strategies folder per each Exchange-symbol-timeframe


def get_training_and_testing_candles(start_date_str: str, finish_date_str: str):
    start_date = jh.arrow_to_timestamp(arrow.get(start_date_str, 'YYYY-MM-DD'))
    finish_date = jh.arrow_to_timestamp(arrow.get(finish_date_str, 'YYYY-MM-DD')) - 60000

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
