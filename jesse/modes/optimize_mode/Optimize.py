import os
from abc import ABC
from datetime import timedelta
from multiprocessing import Manager, Process, cpu_count
from random import choices, randint

import click
import numpy as np
import pydash
from pandas import json_normalize
from timeloop import Timeloop

import jesse.helpers as jh
import jesse.services.logger as logger
from jesse import exceptions, sync_publish
from jesse.modes.optimize_mode.fitness import create_baby, get_and_add_fitness_to_the_bucket
from jesse.routes import router
from jesse.services.progressbar import Progressbar
from jesse.services.redis import is_process_active
from jesse.store import store


class Optimizer(ABC):
    def __init__(
            self,
            training_warmup_candles: dict,
            training_candles: dict,
            testing_warmup_candles: dict,
            testing_candles: dict,
            fast_mode: bool,
            optimal_total: int,
            cpu_cores: int,
            csv: bool,
            export_json: bool,
            start_date: str,
            finish_date: str,
            charset: str = r'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]^_`abcdefghijklmnopqrstuvw',
            fitness_goal: float = 1,
    ) -> None:
        if len(router.routes) != 1:
            raise NotImplementedError('optimize_mode mode only supports one route at the moment')

        self.strategy_name = router.routes[0].strategy_name
        self.exchange = router.routes[0].exchange
        self.symbol = router.routes[0].symbol
        self.timeframe = router.routes[0].timeframe
        strategy_class = jh.get_strategy_class(self.strategy_name)
        self.strategy_hp = strategy_class.hyperparameters(None)
        solution_len = len(self.strategy_hp)

        if solution_len == 0:
            raise exceptions.InvalidStrategy('Targeted strategy does not implement a valid hyperparameters() method.')

        self.started_index = 0
        self.start_time = jh.now_to_timestamp()
        self.population = []
        self.iterations = 2000 * solution_len
        self.population_size = solution_len * 100
        self.solution_len = solution_len
        self.charset = charset
        self.fitness_goal = fitness_goal
        self.fast_mode = fast_mode
        self.cpu_cores = 0
        self.optimal_total = optimal_total
        self.training_warmup_candles = training_warmup_candles
        self.training_candles = training_candles
        self.testing_warmup_candles = testing_warmup_candles
        self.testing_candles = testing_candles
        self.average_execution_seconds = 0

        client_id = jh.get_session_id()
        # check for termination event once per second
        tl_0 = Timeloop()
        @tl_0.job(interval=timedelta(seconds=1))
        def check_for_termination():
            if is_process_active(client_id) is False:
                raise exceptions.Termination
        tl_0.start()

        options = {
            'strategy_name': self.strategy_name,
            'exchange': self.exchange,
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'strategy_hp': self.strategy_hp,
            'csv': csv,
            'json': export_json,
            'start_date': start_date,
            'finish_date': finish_date,
        }

        self.options = {} if options is None else options
        os.makedirs('./storage/temp/optimize', exist_ok=True)
        # self.temp_path = f"./storage/temp/optimize/{self.options['strategy_name']}-{self.options['exchange']}-{self.options['symbol']}-{self.options['timeframe']}-{self.options['start_date']}-{self.options['finish_date']}.pickle"

        if fitness_goal > 1 or fitness_goal < 0:
            raise ValueError('fitness scores must be between 0 and 1')

        if not optimal_total > 0:
            raise ValueError('optimal_total must be bigger than 0')

        # # if temp file exists, load data to resume previous session
        # if jh.file_exists(self.temp_path) and click.confirm(
        #         'Previous session detected. Do you want to resume?', default=True
        # ):
        #     self.load_progress()

        if cpu_cores > cpu_count():
            raise ValueError(f'Entered cpu cores number is more than available on this machine which is {cpu_count()}')
        elif cpu_cores == 0:
            self.cpu_cores = cpu_count()
        else:
            self.cpu_cores = cpu_cores

    def generate_initial_population(self) -> None:
        """
        generates the initial population
        """
        length = int(self.population_size / self.cpu_cores)

        progressbar = Progressbar(length)
        for i in range(length):
            people = []
            with Manager() as manager:
                dna_bucket = manager.list([])
                workers = []

                try:
                    for _ in range(self.cpu_cores):
                        dna = ''.join(choices(self.charset, k=self.solution_len))
                        w = Process(
                            target=get_and_add_fitness_to_the_bucket,
                            args=(
                                dna_bucket, jh.get_config('env.optimization'), router.formatted_routes, router.formatted_data_routes,
                                self.strategy_hp, dna, self.training_warmup_candles, self.training_candles, self.testing_warmup_candles, self.testing_candles,
                                self.optimal_total, self.fast_mode
                            )
                        )
                        w.start()
                        workers.append(w)

                    # join workers
                    for w in workers:
                        w.join()
                        if w.exitcode > 0:
                            logger.error(f'a process exited with exitcode: {w.exitcode}')
                except exceptions.Termination:
                    self._handle_termination(manager, workers)

                for d in dna_bucket:
                    people.append({
                        'dna': d[0],
                        'fitness': d[1],
                        'training_log': d[2],
                        'testing_log': d[3]
                    })

            # update dashboard
            self.update_progressbar(progressbar)

            # general_info streams
            general_info = {
                'started_at': jh.timestamp_to_arrow(self.start_time).humanize(),
                'index': f'{(i + 1) * self.cpu_cores}/{self.population_size}',
                'errors_info_count': f'{len(store.logs.errors)}/{len(store.logs.info)}',
                'trading_route': f'{router.routes[0].exchange}, {router.routes[0].symbol}, {router.routes[0].timeframe}, {router.routes[0].strategy_name}',
                'average_execution_seconds': self.average_execution_seconds
            }
            if jh.is_debugging():
                general_info['population_size'] = self.population_size
                general_info['iterations'] = self.iterations
                general_info['solution_length'] = self.solution_len
            sync_publish('general_info', general_info)

            for p in people:
                self.population.append(p)

        sync_publish('progressbar', {
            'current': 100,
            'estimated_remaining_seconds': 0
        })
        # sort the population
        self.population = list(sorted(self.population, key=lambda x: x['fitness'], reverse=True))

    def select_person(self) -> dict:
        # len(self.population) instead of self.population_size because some DNAs might not have been created due to errors
        # to fix an issue with being less than 100 population_len (which means there's only on hyperparameter in the strategy)
        population_len = len(self.population)
        if population_len == 0:
            raise IndexError('population is empty')
        count = int(population_len / 100)
        if count == 0:
            count = 1
        random_index = np.random.choice(population_len, count, replace=False)
        chosen_ones = [self.population[r] for r in random_index]
        return pydash.max_by(chosen_ones, 'fitness')

    def evolve(self) -> list:
        """
        the main method, that runs the evolutionary algorithm
        """
        # clear the logs to start from a clean slate
        jh.clear_file('storage/logs/optimize-mode.txt')

        logger.log_optimize_mode('Optimization session started')

        if self.started_index == 0:
            logger.log_optimize_mode(
                f"Generating {self.population_size} population size (random DNAs) using {self.cpu_cores} CPU cores"
            )
            self.generate_initial_population()

            if len(self.population) < 0.5 * self.population_size:
                msg = f'Too many errors! less than half of the expected population size could be generated. Only {len(self.population)} individuals from planned {self.population_size} are usable. Read more at https://jesse.trade/help/faq/bad-optimization-results-or-valueerror-too-many-errors-less-than-half-of-the-expected-population-size-could-be-generated'
                logger.log_optimize_mode(msg)
                raise ValueError(msg)

            # if even our best individual is too weak, then we better not continue
            if self.population[0]['fitness'] == 0.0001:
                msg = 'Cannot continue because no individual with the minimum fitness-score was found. Your strategy seems to be flawed or maybe it requires modifications. '
                logger.log_optimize_mode(msg)
                raise exceptions.InvalidStrategy(msg)

        loop_length = int(self.iterations / self.cpu_cores)

        i = self.started_index
        progressbar = Progressbar(loop_length)
        while i < loop_length:
            with Manager() as manager:
                people_bucket = manager.list([])
                workers = []

                try:
                    for _ in range(self.cpu_cores):
                        mommy = self.select_person()
                        daddy = self.select_person()
                        w = Process(
                            target=create_baby,
                            args=(
                                people_bucket, mommy, daddy, self.solution_len, self.charset,
                                jh.get_config('env.optimization'), router.formatted_routes,
                                router.formatted_data_routes,
                                self.strategy_hp, self.training_warmup_candles, self.training_candles, self.testing_warmup_candles, self.testing_candles,
                                self.optimal_total, self.fast_mode
                            )
                        )
                        w.start()
                        workers.append(w)

                    for w in workers:
                        w.join()
                        if w.exitcode > 0:
                            logger.error(f'a process exited with exitcode: {w.exitcode}')
                except exceptions.Termination:
                    self._handle_termination(manager, workers)

                # update dashboard
                click.clear()
                self.update_progressbar(progressbar)
                # general_info streams
                general_info = {
                    'started_at': jh.timestamp_to_arrow(self.start_time).humanize(),
                    'index': f'{(i + 1) * self.cpu_cores}/{self.iterations}',
                    'errors_info_count': f'{len(store.logs.errors)}/{len(store.logs.info)}',
                    'trading_route': f'{router.routes[0].exchange}, {router.routes[0].symbol}, {router.routes[0].timeframe}, {router.routes[0].strategy_name}',
                    'average_execution_seconds': self.average_execution_seconds
                }
                if jh.is_debugging():
                    general_info['population_size'] = self.population_size
                    general_info['iterations'] = self.iterations
                    general_info['solution_length'] = self.solution_len
                sync_publish('general_info', general_info)

                if self.population_size > 50:
                    number_of_ind_to_show = 40
                elif self.population_size > 20:
                    number_of_ind_to_show = 15
                elif self.population_size > 9:
                    number_of_ind_to_show = 9
                else:
                    raise ValueError('self.population_size cannot be less than 10')

                best_candidates = [{
                        'rank': j + 1,
                        'dna': self.population[j]['dna'],
                        'fitness': round(self.population[j]['fitness'], 4),
                        'training_win_rate': self.population[j]['training_log']['win-rate'],
                        'training_total_trades': self.population[j]['training_log']['total'],
                        'training_pnl': self.population[j]['training_log']['PNL'],
                        'testing_win_rate': self.population[j]['testing_log']['win-rate'],
                        'testing_total_trades': self.population[j]['testing_log']['total'],
                        'testing_pnl': self.population[j]['testing_log']['PNL'],
                    } for j in range(number_of_ind_to_show)]
                sync_publish('best_candidates', best_candidates)

                # one person has to die and be replaced with the newborn baby
                for baby in people_bucket:
                    # never kill our best performer
                    random_index = randint(1, len(self.population) - 1)
                    self.population[random_index] = baby
                    self.population = list(sorted(self.population, key=lambda x: x['fitness'], reverse=True))

                    # reaching the fitness goal could also end the process
                    if baby['fitness'] >= self.fitness_goal:
                        self.update_progressbar(progressbar, finished=True)
                        sync_publish('alert', {
                            'message': f'Fitness goal reached after iteration {i*self.cpu_cores}',
                            'type': 'success'
                        })
                        return baby

                # TODO: bring back progress resumption
                # # save progress after every n iterations
                # if i != 0 and int(i * self.cpu_cores) % 50 == 0:
                #     self.save_progress(i)

                # TODO: bring back
                # # store a take_snapshot of the fittest individuals of the population
                # if i != 0 and i % int(100 / self.cpu_cores) == 0:
                #     self.take_snapshot(i * self.cpu_cores)

                i += 1

                logger.log_optimize_mode('Saving to CSV file...')
                study_name = f"{self.options['strategy_name']}-{self.options['exchange']}-{self.options['symbol']}-{self.options['timeframe']}-{self.options['start_date']}-{self.options['finish_date']}"

                dna_json = {'snapshot': []}
                index = f'{(i + 1) * self.cpu_cores}/{self.population_size}'
                for i in range(30):
                    dna_json['snapshot'].append(
                        {'iteration': index, 'dna': self.population[i]['dna'], 'fitness': self.population[i]['fitness'],
                            'training_log': self.population[i]['training_log'], 'testing_log': self.population[i]['testing_log'],
                            'parameters': jh.dna_to_hp(self.options['strategy_hp'], self.population[i]['dna'])})

                path = f'./storage/genetics/{study_name}.txt'
                os.makedirs('./storage/genetics', exist_ok=True)
                txt = ''
                with open(path, 'a', encoding="utf-8") as f:
                    txt += '\n\n'
                    txt += f'# iteration {index}'
                    txt += '\n'

                    for i in range(30):
                        log = f"win-rate: {self.population[i]['training_log']['win-rate']} %, total: {self.population[i]['training_log']['total']}, PNL: {self.population[i]['training_log']['PNL']} % || win-rate: {self.population[i]['testing_log']['win-rate']} %, total: {self.population[i]['testing_log']['total']}, PNL: {self.population[i]['testing_log']['PNL']} %"

                        txt += '\n'
                        txt += f"{i + 1} ==  {self.population[i]['dna']}  ==  {self.population[i]['fitness']}  ==  {log}"

                    f.write(txt)

                path = f'storage/genetics/csv/{study_name}.csv'
                os.makedirs('./storage/genetics/csv', exist_ok=True)
                exists = os.path.exists(path)

                df = json_normalize(dna_json['snapshot'])

                with open(path, 'a', newline='', encoding="utf-8") as outfile:
                    if not exists:
                        # header of CSV file
                        df.to_csv(outfile, header=True, index=False, encoding='utf-8')

                    df.to_csv(outfile, header=False, index=False, encoding='utf-8')

        sync_publish('alert', {
            'message': f"Finished {self.iterations} iterations. Check your best DNA candidates, "
                       f"if you don't like any of them, try modifying your strategy.",
            'type': 'success'
        })

        return self.population

    def run(self) -> list:
        return self.evolve()

    @staticmethod
    def _handle_termination(manager, workers):
        logger.info('Terminating session...')

        # terminate all workers
        for w in workers:
            w.terminate()

        # shutdown the manager process manually since garbage collection cannot won't get to do it for us
        manager.shutdown()

        # now we can terminate the main session safely
        raise exceptions.Termination

    def update_progressbar(self, progressbar, finished=False):
        if finished:
            progressbar.finish()
        else:
            progressbar.update()
        self.average_execution_seconds = progressbar.average_execution_seconds / self.cpu_cores
        sync_publish('progressbar', {
            'current': progressbar.current,
            'estimated_remaining_seconds': progressbar.estimated_remaining_seconds
        })


    # def save_progress(self, iterations_index: int) -> None:
    #     """
    #     pickles data so we can later resume optimizing
    #     """
    #     data = {
    #         'population': self.population,
    #         'iterations': self.iterations,
    #         'iterations_index': iterations_index,
    #         'population_size': self.population_size,
    #         'solution_len': self.solution_len,
    #         'charset': self.charset,
    #         'fitness_goal': self.fitness_goal,
    #         'options': self.options,
    #     }
    #
    #     with open(self.temp_path, 'wb') as f:
    #         pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)

    # def load_progress(self) -> None:
    #     """
    #     Unpickles data to resume from previous optimizing session population
    #     """
    #     with open(self.temp_path, 'rb') as f:
    #         data = pickle.load(f)
    #
    #     self.population = data['population']
    #     self.iterations = data['iterations']
    #     self.started_index = data['iterations_index']
    #     self.population_size = data['population_size']
    #     self.solution_len = data['solution_len']
    #     self.charset = data['charset']
    #     self.fitness_goal = data['fitness_goal']
    #     self.options = data['options']

    # def take_snapshot(self, index: int) -> None:
    #     """
    #     stores a snapshot of the fittest population members into a file.
    #     """
    #     study_name = f"{self.options['strategy_name']}-{self.options['exchange']}-{self.options['symbol']}-{self.options['timeframe']}-{self.options['start_date']}-{self.options['finish_date']}"
    #
    #     dna_json = {'snapshot': []}
    #     for i in range(30):
    #         dna_json['snapshot'].append(
    #             {'iteration': index, 'dna': self.population[i]['dna'], 'fitness': self.population[i]['fitness'],
    #              'training_log': self.population[i]['training_log'], 'testing_log': self.population[i]['testing_log'],
    #              'parameters': jh.dna_to_hp(self.options['strategy_hp'], self.population[i]['dna'])})
    #
    #     path = f'./storage/genetics/{study_name}.txt'
    #     os.makedirs('./storage/genetics', exist_ok=True)
    #     txt = ''
    #     with open(path, 'a', encoding="utf-8") as f:
    #         txt += '\n\n'
    #         txt += f'# iteration {index}'
    #         txt += '\n'
    #
    #         for i in range(30):
    #             log = f"win-rate: {self.population[i]['training_log']['win-rate']} %, total: {self.population[i]['training_log']['total']}, PNL: {self.population[i]['training_log']['PNL']} % || win-rate: {self.population[i]['testing_log']['win-rate']} %, total: {self.population[i]['testing_log']['total']}, PNL: {self.population[i]['testing_log']['PNL']} %"
    #
    #             txt += '\n'
    #             txt += f"{i + 1} ==  {self.population[i]['dna']}  ==  {self.population[i]['fitness']}  ==  {log}"
    #
    #         f.write(txt)
    #
    #     if self.options['csv']:
    #         path = f'storage/genetics/csv/{study_name}.csv'
    #         os.makedirs('./storage/genetics/csv', exist_ok=True)
    #         exists = os.path.exists(path)
    #
    #         df = json_normalize(dna_json['snapshot'])
    #
    #         with open(path, 'a', newline='', encoding="utf-8") as outfile:
    #             if not exists:
    #                 # header of CSV file
    #                 df.to_csv(outfile, header=True, index=False, encoding='utf-8')
    #
    #             df.to_csv(outfile, header=False, index=False, encoding='utf-8')
    #
    #     if self.options['json']:
    #         path = f'storage/genetics/json/{study_name}.json'
    #         os.makedirs('./storage/genetics/json', exist_ok=True)
    #         exists = os.path.exists(path)
    #
    #         mode = 'r+' if exists else 'w'
    #         with open(path, mode, encoding="utf-8") as file:
    #             if not exists:
    #                 snapshots = {"snapshots": []}
    #                 snapshots["snapshots"].append(dna_json['snapshot'])
    #                 json.dump(snapshots, file, ensure_ascii=False)
    #             else:
    #                 # file exists - append
    #                 file.seek(0)
    #                 data = json.load(file)
    #                 data["snapshots"].append(dna_json['snapshot'])
    #                 file.seek(0)
    #                 json.dump(data, file, ensure_ascii=False)
    #             file.write('\n')
