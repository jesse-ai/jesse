import pickle
from abc import ABC
from random import randint, choices, choice
from typing import Dict, Union, Any, List
from jesse import sync_publish
from jesse.services.redis import process_status
from multiprocessing import Process, Manager
import click
import numpy as np
import pydash
import jesse.helpers as jh
from jesse.services import table
import jesse.services.logger as logger
from jesse.store import store
import jesse.services.report as report
import traceback
import os
import json
from pandas import json_normalize
from jesse import exceptions
from .fitness import get_and_add_fitness_to_the_bucket, get_fitness
from jesse.routes import router
from numpy import ndarray
from multiprocessing import cpu_count


class Optimizer(ABC):
    def __init__(
            self,
            training_candles: ndarray, testing_candles: ndarray,
            optimal_total: int, cpu_cores: int,
            csv: bool,
            json: bool,
            start_date: str, finish_date: str,
            charset: str = r'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]^_`abcdefghijklmnopqrstuvw',
            fitness_goal: float = 1,
    ) -> None:
        if len(router.routes) != 1:
            raise NotImplementedError('optimize_mode mode only supports one route at the moment')

        self.strategy_name = router.routes[0].strategy_name
        self.exchange = router.routes[0].exchange
        self.symbol = router.routes[0].symbol
        self.timeframe = router.routes[0].timeframe
        StrategyClass = jh.get_strategy_class(self.strategy_name)
        self.strategy_hp = StrategyClass.hyperparameters(None)
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
        self.cpu_cores = 0
        self.optimal_total = optimal_total
        self.training_candles = training_candles
        self.testing_candles = testing_candles

        options = {
            'strategy_name': self.strategy_name,
            'exchange': self.exchange,
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'strategy_hp': self.strategy_hp,
            'csv': csv,
            'json': json,
            'start_date': start_date,
            'finish_date': finish_date,
        }

        self.options = {} if options is None else options
        os.makedirs('./storage/temp/optimize', exist_ok=True)
        self.temp_path = f"./storage/temp/optimize/{self.options['strategy_name']}-{self.options['exchange']}-{self.options['symbol']}-{self.options['timeframe']}-{self.options['start_date']}-{self.options['finish_date']}.pickle"

        if fitness_goal > 1 or fitness_goal < 0:
            raise ValueError('fitness scores must be between 0 and 1')

        # if temp file exists, load data to resume previous session
        if jh.file_exists(self.temp_path) and click.confirm(
                'Previous session detected. Do you want to resume?', default=True
        ):
            self.load_progress()

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

        with click.progressbar(length=length, label='Generating initial population...') as progressbar:
            for i in range(length):
                people = []
                with Manager() as manager:
                    dna_bucket = manager.list([])
                    workers = []

                    try:
                        for _ in range(self.cpu_cores):
                            # check for termination event once per second
                            if process_status() != 'started':
                                raise exceptions.Termination

                            dna = ''.join(choices(self.charset, k=self.solution_len))
                            w = Process(
                                target=get_and_add_fitness_to_the_bucket,
                                args=(
                                    dna_bucket, jh.get_config('env.optimization'), router.formatted_routes, router.formatted_extra_routes,
                                    self.strategy_hp, dna, self.training_candles, self.testing_candles,
                                    self.optimal_total
                                )
                            )
                            w.start()
                            workers.append(w)

                        # join workers
                        for w in workers:
                            w.join()
                            if w.exitcode > 0:
                                logger.error(f'a process exited with exitcode: {str(w.exitcode)}')
                    except exceptions.Termination:
                        self._handle_termination(manager, workers)
                    except:
                        raise

                    for d in dna_bucket:
                        people.append({
                            'dna': d[0],
                            'fitness': d[1],
                            'training_log': d[2],
                            'testing_log': d[3]
                        })

                # update dashboard
                click.clear()
                progressbar.update(1)
                sync_publish('progressbar', {
                    'current': round(i / length * 100, 1),
                    'estimated_remaining_seconds': progressbar.eta
                })
                print('\n')

                table_items = [
                    ['Started at', jh.timestamp_to_arrow(self.start_time).humanize()],
                    ['Index', f'{len(self.population)}/{self.population_size}'],
                    ['errors/info', f'{len(store.logs.errors)}/{len(store.logs.info)}'],
                    ['Trading Route',
                     f'{router.routes[0].exchange}, {router.routes[0].symbol}, {router.routes[0].timeframe}, {router.routes[0].strategy_name}'],
                    # TODO: add generated DNAs?
                    # ['-'*10, '-'*10],
                    # ['DNA', people[0]['dna']],
                    # ['fitness', round(people[0]['fitness'], 6)],
                    # ['training|testing logs', people[0]['log']],
                ]
                if jh.is_debugging():
                    table_items.insert(3, ['Population Size', self.population_size])
                    table_items.insert(3, ['Iterations', self.iterations])
                    table_items.insert(3, ['Solution Length', self.solution_len])
                    table_items.insert(3, ['-' * 10, '-' * 10])

                table.key_value(table_items, 'Optimize Mode', alignments=('left', 'right'))

                general_info = {
                    'started_at': jh.timestamp_to_arrow(self.start_time).humanize(),
                    'index': f'{len(self.population)}/{self.population_size}',
                    'errors_info_count': f'{len(store.logs.errors)}/{len(store.logs.info)}',
                    'trading_route': f'{router.routes[0].exchange}, {router.routes[0].symbol}, {router.routes[0].timeframe}, {router.routes[0].strategy_name}',
                }
                if jh.is_debugging():
                    general_info['population_size'] = self.population_size
                    general_info['iterations'] = self.iterations
                    general_info['solution_length'] = self.solution_len

                sync_publish('general_info', general_info)

                # errors
                if jh.is_debugging() and len(report.errors()):
                    print('\n')
                    table.key_value(report.errors(), 'Error Logs')

                for p in people:
                    self.population.append(p)
            sync_publish('progressbar', {
                'current': 100,
                'estimated_remaining_seconds': 0
            })
        # sort the population
        self.population = list(sorted(self.population, key=lambda x: x['fitness'], reverse=True))

    def mutate(self, baby: Dict[str, Union[str, Any]]) -> Dict[str, Union[str, Any]]:
        replace_at = randint(0, self.solution_len - 1)
        replace_with = choice(self.charset)
        dna = f"{baby['dna'][:replace_at]}{replace_with}{baby['dna'][replace_at + 1:]}"

        try:
            # check if already exists and then return it
            return next(item for item in self.population if item["dna"] == dna)
        except StopIteration:
            # not found - so run the backtest
            fitness_score, fitness_log_training, fitness_log_testing = get_fitness(
                self.strategy_hp, dna, self.training_candles, self.testing_candles, self.optimal_total
            )

        return {
            'dna': dna,
            'fitness': fitness_score,
            'training_log': fitness_log_training,
            'testing_log': fitness_log_testing
        }

    def make_love(self) -> Dict[str, Union[str, Any]]:
        mommy = self.select_person()
        daddy = self.select_person()

        dna = ''.join(
            daddy['dna'][i] if i % 2 == 0 else mommy['dna'][i]
            for i in range(self.solution_len)
        )

        try:
            # check if already exists and then return it
            return next(item for item in self.population if item["dna"] == dna)
        except StopIteration:
            # not found - so run the backtest
            fitness_score, fitness_log_training, fitness_log_testing = get_fitness(
                self.strategy_hp, dna, self.training_candles, self.testing_candles, self.optimal_total
            )

        return {
            'dna': dna,
            'fitness': fitness_score,
            'training_log': fitness_log_training,
            'testing_log': fitness_log_testing
        }

    def select_person(self) -> Dict[str, Union[str, Any]]:
        # len(self.population) instead of self.population_size because some DNAs might not have been created due errors
        random_index = np.random.choice(len(self.population), int(len(self.population) / 100), replace=False)
        chosen_ones = [self.population[r] for r in random_index]

        return pydash.max_by(chosen_ones, 'fitness')

    def evolve(self) -> List[Any]:
        """
        the main method, that runs the evolutionary algorithm
        """
        # generate the population if starting
        if self.started_index == 0:
            self.generate_initial_population()
            if len(self.population) < 0.5 * self.population_size:
                raise ValueError('Too many errors! less than half of the expected population size could be generated.')

            # if even our best individual is too weak, then we better not continue
            if self.population[0]['fitness'] == 0.0001:
                raise exceptions.InvalidStrategy(
                    'Cannot continue because no individual with the minimum fitness-score was found. '
                    'Your strategy seems to be flawed or maybe it requires modifications. ')

        loop_length = int(self.iterations / self.cpu_cores)

        i = self.started_index
        with click.progressbar(length=loop_length, label='Evolving...') as progressbar:
            while i < loop_length:
                with Manager() as manager:
                    people = manager.list([])
                    workers = []

                    def get_baby(people: List) -> None:
                        try:
                            # let's make a baby together LOL
                            baby = self.make_love()
                            # let's mutate baby's genes, who knows, maybe we create a x-man or something
                            baby = self.mutate(baby)
                            people.append(baby)
                        except Exception as e:
                            proc = os.getpid()
                            logger.error(f'process failed - ID: {str(proc)}')
                            logger.error("".join(traceback.TracebackException.from_exception(e).format()))
                            raise e

                    try:
                        for _ in range(self.cpu_cores):
                            # check for termination event once per second
                            if process_status() != 'started':
                                raise exceptions.Termination

                            w = Process(target=get_baby, args=[people])
                            w.start()
                            workers.append(w)

                        for w in workers:
                            w.join()
                            if w.exitcode > 0:
                                logger.error(f'a process exited with exitcode: {str(w.exitcode)}')
                    except exceptions.Termination:
                        self._handle_termination(manager, workers)
                    except:
                        raise

                    # update dashboard
                    click.clear()
                    progressbar.update(1)
                    print('\n')
                    from jesse.routes import router
                    table_items = [
                        ['Started At', jh.timestamp_to_arrow(self.start_time).humanize()],
                        ['Index/Total', f'{(i + 1) * self.cpu_cores}/{self.iterations}'],
                        ['errors/info', f'{len(store.logs.errors)}/{len(store.logs.info)}'],
                        ['Route',
                         f'{router.routes[0].exchange}, {router.routes[0].symbol}, {router.routes[0].timeframe}, {router.routes[0].strategy_name}']
                    ]
                    if jh.is_debugging():
                        table_items.insert(
                            3,
                            ['Population Size, Solution Length',
                             f'{self.population_size}, {self.solution_len}']
                        )

                    table.key_value(table_items, 'info', alignments=('left', 'right'))

                    # errors
                    if jh.is_debugging() and len(report.errors()):
                        print('\n')
                        table.key_value(report.errors(), 'Error Logs')

                    print('\n')
                    print('Best DNA candidates:')
                    print('\n')

                    # print fittest individuals
                    if jh.is_debugging():
                        fittest_list = [['Rank', 'DNA', 'Fitness', 'Training log || Testing log'], ]
                    else:
                        fittest_list = [['Rank', 'DNA', 'Training log || Testing log'], ]
                    if self.population_size > 50:
                        number_of_ind_to_show = 15
                    elif self.population_size > 20:
                        number_of_ind_to_show = 10
                    elif self.population_size > 9:
                        number_of_ind_to_show = 9
                    else:
                        raise ValueError('self.population_size cannot be less than 10')

                    for j in range(number_of_ind_to_show):
                        log = f"win-rate: {self.population[j]['training_log']['win-rate']}%, total: {self.population[j]['training_log']['total']}, PNL: {self.population[j]['training_log']['PNL']}% || win-rate: {self.population[j]['testing_log']['win-rate']}%, total: {self.population[j]['testing_log']['total']}, PNL: {self.population[j]['testing_log']['PNL']}%"
                        if self.population[j]['testing_log']['PNL'] is not None and self.population[j]['training_log'][
                            'PNL'] > 0 and self.population[j]['testing_log']['PNL'] > 0:
                            log = jh.style(log, 'bold')
                        if jh.is_debugging():
                            fittest_list.append(
                                [
                                    j + 1,
                                    self.population[j]['dna'],
                                    self.population[j]['fitness'],
                                    log
                                ],
                            )
                        else:
                            fittest_list.append(
                                [
                                    j + 1,
                                    self.population[j]['dna'],
                                    log
                                ],
                            )

                    if jh.is_debugging():
                        table.multi_value(fittest_list, with_headers=True, alignments=('left', 'left', 'right', 'left'))
                    else:
                        table.multi_value(fittest_list, with_headers=True, alignments=('left', 'left', 'left'))

                    # one person has to die and be replaced with the newborn baby
                    for baby in people:
                        random_index = randint(1, len(self.population) - 1)  # never kill our best perforemr
                        try:
                            self.population[random_index] = baby
                        except IndexError:
                            print('=============')
                            print(f'self.population_size: {self.population_size}')
                            print(f'self.population length: {len(self.population)}')
                            jh.terminate_app()

                        self.population = list(sorted(self.population, key=lambda x: x['fitness'], reverse=True))

                        # reaching the fitness goal could also end the process
                        if baby['fitness'] >= self.fitness_goal:
                            progressbar.update(self.iterations - i)
                            print('\n')
                            print(f'fitness goal reached after iteration {i}')
                            return baby

                    # save progress after every n iterations
                    if i != 0 and int(i * self.cpu_cores) % 50 == 0:
                        self.save_progress(i)

                    # store a take_snapshot of the fittest individuals of the population
                    if i != 0 and i % int(100 / self.cpu_cores) == 0:
                        self.take_snapshot(i * self.cpu_cores)

                    i += 1

        print('\n\n')
        print(f'Finished {self.iterations} iterations.')
        return self.population

    def run(self) -> List[Any]:
        return self.evolve()

    def save_progress(self, iterations_index: int) -> None:
        """
        pickles data so we can later resume optimizing
        """
        data = {
            'population': self.population,
            'iterations': self.iterations,
            'iterations_index': iterations_index,
            'population_size': self.population_size,
            'solution_len': self.solution_len,
            'charset': self.charset,
            'fitness_goal': self.fitness_goal,
            'options': self.options,
        }

        with open(self.temp_path, 'wb') as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)

    def load_progress(self) -> None:
        """
        unpickles data to resume from previous optimizing session population
        """
        with open(self.temp_path, 'rb') as f:
            data = pickle.load(f)

        self.population = data['population']
        self.iterations = data['iterations']
        self.started_index = data['iterations_index']
        self.population_size = data['population_size']
        self.solution_len = data['solution_len']
        self.charset = data['charset']
        self.fitness_goal = data['fitness_goal']
        self.options = data['options']

    def take_snapshot(self, index: int) -> None:
        """
        stores a snapshot of the fittest population members into a file.
        """
        study_name = f"{self.options['strategy_name']}-{self.options['exchange']}-{self.options['symbol']}-{self.options['timeframe']}-{self.options['start_date']}-{self.options['finish_date']}"

        dnas_json = {'snapshot': []}
        for i in range(30):
            dnas_json['snapshot'].append(
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

        if self.options['csv']:
            path = f'storage/genetics/csv/{study_name}.csv'
            os.makedirs('./storage/genetics/csv', exist_ok=True)
            exists = os.path.exists(path)

            df = json_normalize(dnas_json['snapshot'])

            with open(path, 'a', newline='', encoding="utf-8") as outfile:
                if not exists:
                    # header of CSV file
                    df.to_csv(outfile, header=True, index=False, encoding='utf-8')

                df.to_csv(outfile, header=False, index=False, encoding='utf-8')

        if self.options['json']:
            path = f'storage/genetics/json/{study_name}.json'
            os.makedirs('./storage/genetics/json', exist_ok=True)
            exists = os.path.exists(path)

            mode = 'r+' if exists else 'w'
            with open(path, mode, encoding="utf-8") as file:
                if not exists:
                    snapshots = {"snapshots": []}
                    snapshots["snapshots"].append(dnas_json['snapshot'])
                    json.dump(snapshots, file, ensure_ascii=False)
                else:
                    # file exists - append
                    file.seek(0)
                    data = json.load(file)
                    data["snapshots"].append(dnas_json['snapshot'])
                    file.seek(0)
                    json.dump(data, file, ensure_ascii=False)
                file.write('\n')

    @staticmethod
    def _handle_termination(manager, workers):
        print(
            jh.color('Terminating session...', 'red')
        )

        # terminate all workers
        for w in workers:
            w.terminate()

        # shutdown the manager process manually since garbage collection cannot won't get to do it for us
        manager.shutdown()

        # now we can terminate the main session safely
        jh.terminate_app()
