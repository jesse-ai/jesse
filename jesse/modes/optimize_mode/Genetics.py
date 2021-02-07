import multiprocessing
import pickle
import sys
from abc import ABC, abstractmethod
from random import randint, choices, choice

# for macOS only
from typing import Dict, Union, Any, List

if sys.platform == 'darwin':
    multiprocessing.set_start_method('fork')
from multiprocessing import Process, Manager

import click
import numpy as np
import pydash

import jesse.helpers as jh
from jesse.services import table
from jesse.routes import router
import jesse.services.logger as logger
from jesse.store import store
import jesse.services.report as report
import traceback
import os
import json
from pandas import json_normalize


class Genetics(ABC):
    def __init__(self, iterations: int, population_size: int, solution_len: int,
                 charset: str = '()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]^_`abcdefghijklmnopqrstuvw',
                 fitness_goal: float = 1,
                 options: Dict[str, Union[bool, Any]] = None) -> None:
        self.started_index = 0
        self.start_time = jh.now_to_timestamp()
        self.population = []
        self.iterations = iterations
        self.population_size = population_size
        self.solution_len = solution_len
        self.charset = charset
        self.fitness_goal = fitness_goal
        self.cpu_cores = 0

        if options is None:
            self.options = {}
        else:
            self.options = options

        os.makedirs('./storage/temp/optimize', exist_ok=True)
        self.temp_path = './storage/temp/optimize/{}-{}-{}-{}.pickle'.format(
            self.options['strategy_name'], self.options['exchange'],
            self.options['symbol'], self.options['timeframe']
        )

        if fitness_goal > 1 or fitness_goal < 0:
            raise ValueError('fitness scores must be between 0 and 1')

        # if temp file exists, load data to resume previous session
        if jh.file_exists(self.temp_path):
            if click.confirm('Previous session detected. Do you want to resume?', default=True):
                self.load_progress()

    @abstractmethod
    def fitness(self, dna: str) -> tuple:
        """
        calculates and returns the fitness score the the DNA
        """
        pass

    def generate_initial_population(self) -> None:
        """
        generates the initial population
        """
        loop_length = int(self.population_size / self.cpu_cores)

        with click.progressbar(length=loop_length, label='Generating initial population...') as progressbar:
            for i in range(loop_length):
                people = []
                with Manager() as manager:
                    dna_bucket = manager.list([])
                    workers = []

                    def get_fitness(dna: str, dna_bucket: list) -> None:
                        try:
                            fitness_score, fitness_log_training, fitness_log_testing = self.fitness(dna)
                            dna_bucket.append((dna, fitness_score, fitness_log_training, fitness_log_testing))
                        except Exception as e:
                            proc = os.getpid()
                            logger.error('process failed - ID: {}'.format(str(proc)))
                            logger.error("".join(traceback.TracebackException.from_exception(e).format()))
                            raise e

                    try:
                        for _ in range(self.cpu_cores):
                            dna = ''.join(choices(self.charset, k=self.solution_len))
                            w = Process(target=get_fitness, args=(dna, dna_bucket))
                            w.start()
                            workers.append(w)

                        # join workers
                        for w in workers:
                            w.join()
                            if w.exitcode > 0:
                                logger.error('a process exited with exitcode: {}'.format(str(w.exitcode)))
                    except KeyboardInterrupt:
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
                print('\n')

                table_items = [
                    ['Started at', jh.timestamp_to_arrow(self.start_time).humanize()],
                    ['Index', '{}/{}'.format(len(self.population), self.population_size)],
                    ['errors/info', '{}/{}'.format(len(store.logs.errors), len(store.logs.info))],
                    ['Trading Route', '{}, {}, {}, {}'.format(
                        router.routes[0].exchange, router.routes[0].symbol, router.routes[0].timeframe,
                        router.routes[0].strategy_name
                    )],
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

                # errors
                if jh.is_debugging() and len(report.errors()):
                    print('\n')
                    table.key_value(report.errors(), 'Error Logs')

                for p in people:
                    self.population.append(p)

        # sort the population
        self.population = list(sorted(self.population, key=lambda x: x['fitness'], reverse=True))

    def mutate(self, baby: Dict[str, Union[str, Any]]) -> Dict[str, Union[str, Any]]:
        replace_at = randint(0, self.solution_len - 1)
        replace_with = choice(self.charset)
        dna = '{}{}{}'.format(baby['dna'][:replace_at], replace_with, baby['dna'][replace_at + 1:])
        fitness_score, fitness_log_training, fitness_log_testing = self.fitness(dna)
        return {
            'dna': dna,
            'fitness': fitness_score,
            'training_log': fitness_log_training,
            'testing_log': fitness_log_testing
        }

    def make_love(self) -> Dict[str, Union[str, Any]]:
        mommy = self.select_person()
        daddy = self.select_person()

        dna = ''

        for i in range(self.solution_len):
            if i % 2 == 0:
                dna += daddy['dna'][i]
            else:
                dna += mommy['dna'][i]

        fitness_score, fitness_log_training, fitness_log_testing = self.fitness(dna)

        return {
            'dna': dna,
            'fitness': fitness_score,
            'training_log': fitness_log_training,
            'testing_log': fitness_log_testing
        }

    def select_person(self) -> Dict[str, Union[str, Any]]:
        # len(self.population) instead of self.population_size because some DNAs might not have been created due errors
        random_index = np.random.choice(len(self.population), int(len(self.population) / 100), replace=False)
        chosen_ones = []

        for r in random_index:
            chosen_ones.append(self.population[r])

        return pydash.max_by(chosen_ones, 'fitness')

    def evolve(self) -> List[Any]:
        """
        the main method, that runs the evolutionary algorithm
        """
        # generate the population if starting
        if self.started_index == 0:
            self.generate_initial_population()
            if len(self.population) < 0.5 * self.population_size:
                raise ValueError('Too many errors: less then half of the planned population size could be generated.')

            # if even our best individual is too weak, then we better not continue
            if self.population[0]['fitness'] == 0.0001:
                print(jh.color('Cannot continue because no individual with the minimum fitness-score was found. '
                               'Your strategy seems to be flawed or maybe it requires modifications. ', 'yellow'))
                jh.terminate_app()

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
                            logger.error('process failed - ID: {}'.format(str(proc)))
                            logger.error("".join(traceback.TracebackException.from_exception(e).format()))
                            raise e

                    try:
                        for _ in range(self.cpu_cores):
                            w = Process(target=get_baby, args=[people])
                            w.start()
                            workers.append(w)

                        for w in workers:
                            w.join()
                            if w.exitcode > 0:
                                logger.error('a process exited with exitcode: {}'.format(str(w.exitcode)))
                    except KeyboardInterrupt:
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
                    except:
                        raise

                    # update dashboard
                    click.clear()
                    progressbar.update(1)
                    print('\n')

                    table_items = [
                        ['Started At', jh.timestamp_to_arrow(self.start_time).humanize()],
                        ['Index/Total', '{}/{}'.format((i + 1) * self.cpu_cores, self.iterations)],
                        ['errors/info', '{}/{}'.format(len(store.logs.errors), len(store.logs.info))],
                        ['Route', '{}, {}, {}, {}'.format(
                            router.routes[0].exchange, router.routes[0].symbol, router.routes[0].timeframe,
                            router.routes[0].strategy_name
                        )]
                    ]
                    if jh.is_debugging():
                        table_items.insert(
                            3,
                            ['Population Size, Solution Length',
                             '{}, {}'.format(self.population_size, self.solution_len)]
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
                        log = 'win-rate: {}%, total: {}, PNL: {}% || win-rate: {}%, total: {}, PNL: {}%'.format(
                            self.population[j]['training_log']['win-rate'], self.population[j]['training_log']['total'],
                            self.population[j]['training_log']['PNL'], self.population[j]['testing_log']['win-rate'],
                            self.population[j]['testing_log']['total'], self.population[j]['testing_log']['PNL'])
                        if self.population[j]['testing_log']['PNL'] is not None and self.population[j]['training_log'][
                            'PNL'] > 0 and self.population[j]['testing_log'][
                            'PNL'] > 0:
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
                            print('self.population_size: {}'.format(self.population_size))
                            print('self.population length: {}'.format(len(self.population)))
                            jh.terminate_app()

                        self.population = list(sorted(self.population, key=lambda x: x['fitness'], reverse=True))

                        # reaching the fitness goal could also end the process
                        if baby['fitness'] >= self.fitness_goal:
                            progressbar.update(self.iterations - i)
                            print('\n')
                            print('fitness goal reached after iteration {}'.format(i))
                            return baby

                    # save progress after every n iterations
                    if i != 0 and int(i * self.cpu_cores) % 50 == 0:
                        self.save_progress(i)

                    # store a take_snapshot of the fittest individuals of the population
                    if i != 0 and i % int(100 / self.cpu_cores) == 0:
                        self.take_snapshot(i * self.cpu_cores)

                    i += 1

        print('\n\n')
        print('Finished {} iterations.'.format(self.iterations))
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
        study_name = '{}-{}-{}-{}'.format(
            self.options['strategy_name'], self.options['exchange'],
            self.options['symbol'], self.options['timeframe']
        )

        dnas_json = {'snapshot': []}
        for i in range(30):
            dnas_json['snapshot'].append(
                {'iteration': index, 'dna': self.population[i]['dna'], 'fitness': self.population[i]['fitness'],
                 'training_log': self.population[i]['training_log'], 'testing_log': self.population[i]['testing_log'],
                 'parameters': jh.dna_to_hp(self.options['strategy_hp'], self.population[i]['dna'])})

        path = './storage/genetics/{}.txt'.format(study_name)
        os.makedirs('./storage/genetics', exist_ok=True)
        txt = ''
        with open(path, 'a', encoding="utf-8") as f:
            txt += '\n\n'
            txt += '# iteration {}'.format(index)
            txt += '\n'

            for i in range(30):
                log = 'win-rate: {} %, total: {}, PNL: {} % || win-rate: {} %, total: {}, PNL: {} %'.format(
                    self.population[i]['training_log']['win-rate'], self.population[i]['training_log']['total'],
                    self.population[i]['training_log']['PNL'], self.population[i]['testing_log']['win-rate'],
                    self.population[i]['testing_log']['total'], self.population[i]['testing_log']['PNL'])

                txt += '\n'
                txt += "{} ==  {}  ==  {}  ==  {}".format(
                    i + 1, self.population[i]['dna'], self.population[i]['fitness'], log
                )

            f.write(txt)

        if self.options['csv']:
            path = 'storage/genetics/csv/{}.csv'.format(study_name)
            os.makedirs('./storage/genetics/csv', exist_ok=True)
            exists = os.path.exists(path)

            df = json_normalize(dnas_json['snapshot'])

            with open(path, 'a', newline='', encoding="utf-8") as outfile:
                if not exists:
                    # header of CSV file
                    df.to_csv(outfile, header=True, index=False, encoding='utf-8')

                df.to_csv(outfile, header=False, index=False, encoding='utf-8')

        if self.options['json']:
            path = 'storage/genetics/json/{}.json'.format(study_name)
            os.makedirs('./storage/genetics/json', exist_ok=True)
            exists = os.path.exists(path)

            mode = 'r+' if exists else 'w'
            with open(path, mode, encoding="utf-8") as file:
                if not exists:
                    snapshots = {"snapshots": []}
                    snapshots["snapshots"].append(dnas_json['snapshot'])
                    json.dump(snapshots, file, ensure_ascii=False)
                    file.write('\n')
                else:
                    # file exists - append
                    file.seek(0)
                    data = json.load(file)
                    data["snapshots"].append(dnas_json['snapshot'])
                    file.seek(0)
                    json.dump(data, file, ensure_ascii=False)
                    file.write('\n')
