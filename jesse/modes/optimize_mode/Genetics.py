import pickle
from abc import ABC, abstractmethod
from random import randint, choices, choice
import multiprocessing
import sys
import os

# for macOS only
if sys.platform == 'darwin':
    multiprocessing.set_start_method('fork')
from multiprocessing import Process, cpu_count, Manager

import click
import numpy as np
import pydash

import jesse.helpers as jh
from jesse.services import table
from jesse.routes import router


class Genetics(ABC):
    def __init__(self, iterations, population_size, solution_len,
                 charset='()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]^_`abcdefghijklmnopqrstuvw',
                 fitness_goal=1,
                 options=None):
        """
        :param iterations: int
        :param population_size: int
        :param solution_len: int
        :param charset: str default= '()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]^_`abcdefghijklmnopqrstuvw'
        which is 40-119 (len=80)
        :param fitness_goal:
        """
        # used for naming the files related to this session
        self.session_id = str(jh.now())
        self.started_index = 0
        self.start_time = jh.now()
        self.population = []
        self.iterations = iterations
        self.population_size = population_size
        self.solution_len = solution_len
        self.charset = charset
        self.fitness_goal = fitness_goal

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
    def fitness(self, dna) -> tuple:
        """
        calculates and returns the fitness score the the DNA

        :param dna: str
        :return: float
        """
        pass

    def generate_initial_population(self):
        """
        generates the initial population
        """
        cores_num = cpu_count()
        loop_length = int(self.population_size / cores_num)

        with click.progressbar(length=loop_length, label='Generating initial population...') as progressbar:
            for i in range(loop_length):
                people = []
                with Manager() as manager:
                    dna_bucket = manager.list([])
                    workers = []

                    def get_fitness(dna, dna_bucket):
                        fitness_score, fitness_log = self.fitness(dna)
                        dna_bucket.append((dna, fitness_score, fitness_log))

                    for _ in range(cores_num):
                        dna = ''.join(choices(self.charset, k=self.solution_len))
                        w = Process(target=get_fitness, args=(dna, dna_bucket))
                        w.start()
                        workers.append(w)

                    # join workers
                    for w in workers:
                        w.join()

                    for d in dna_bucket:
                        people.append({
                            'dna': d[0],
                            'fitness': d[1],
                            'log': d[2]
                        })

                # update dashboard
                click.clear()
                progressbar.update(1)
                print('\n')
                table.key_value([
                    ['started at', jh.get_arrow(self.start_time).humanize()],
                    ['index/total', '{}/{}'.format(len(self.population), self.population_size)],
                    ['-', '-'],
                    ['population_size', self.population_size],
                    ['iterations', self.iterations],
                    ['solution_len', self.solution_len],
                    ['route', '{}, {}, {}, {}'.format(
                        router.routes[0].exchange, router.routes[0].symbol, router.routes[0].timeframe,
                        router.routes[0].strategy_name
                    )],
                    ['-', '-'],
                    ['DNA', people[0]['dna']],
                    ['fitness', round(people[0]['fitness'], 6)],
                    ['training|testing logs', people[0]['log']],
                ], 'baby', alignments=('left', 'right'))

                for p in people:
                    self.population.append(p)

        # sort the population
        self.population = list(sorted(self.population, key=lambda x: x['fitness'], reverse=True))

    def mutate(self, baby):
        replace_at = randint(0, self.solution_len - 1)
        replace_with = choice(self.charset)
        dna = '{}{}{}'.format(baby['dna'][:replace_at], replace_with, baby['dna'][replace_at + 1:])
        fitness_score, fitness_log = self.fitness(dna)

        return {
            'dna': dna,
            'fitness': fitness_score,
            'log': fitness_log
        }

    def make_love(self):
        mommy = self.select_person()
        daddy = self.select_person()

        dna = ''

        for i in range(self.solution_len):
            if i % 2 == 0:
                dna += daddy['dna'][i]
            else:
                dna += mommy['dna'][i]

        fitness_score, fitness_log = self.fitness(dna)

        return {
            'dna': dna,
            'fitness': fitness_score,
            'log': fitness_log
        }

    def select_person(self):
        random_index = np.random.choice(self.population_size, int(self.population_size / 100), replace=False)
        chosen_ones = []

        for r in random_index:
            chosen_ones.append(self.population[r])

        return pydash.max_by(chosen_ones, 'fitness')

    def evolve(self):
        """
        the main method, that runs the evolutionary algorithm
        """
        # generate the population if starting
        if self.started_index == 0:
            self.generate_initial_population()

        cores_num = cpu_count()
        loop_length = int(self.iterations / cores_num)

        i = self.started_index
        with click.progressbar(length=loop_length, label='Evolving...') as progressbar:
            while i < loop_length:
                with Manager() as manager:
                    people = manager.list([])
                    workers = []

                    def get_baby(people):
                        # let's make a baby together LOL
                        baby = self.make_love()
                        # let's mutate baby's genes, who knows, maybe we create a x-man or something
                        baby = self.mutate(baby)
                        people.append(baby)

                    for _ in range(cores_num):
                        w = Process(target=get_baby, args=[people])
                        w.start()
                        workers.append(w)

                    for w in workers:
                        w.join()

                    # update dashboard
                    click.clear()
                    progressbar.update(1)
                    print('\n')

                    table.key_value([
                        ['started at', jh.get_arrow(self.start_time).humanize()],
                        ['index/total', '{}/{}'.format((i + 1) * cores_num, self.iterations)],
                        ['population_size, solution_len', '{}, {}'.format(self.population_size, self.solution_len)],
                        ['route', '{}, {}, {}, {}'.format(
                            router.routes[0].exchange, router.routes[0].symbol, router.routes[0].timeframe,
                            router.routes[0].strategy_name
                        )]
                    ], 'info', alignments=('left', 'right'))

                    print('\n')

                    # print fittest individuals
                    fittest_list = [['rank', 'DNA', 'fitness', 'training|testing logs'], ]
                    if self.population_size > 50:
                        number_of_ind_to_show = 25
                    elif self.population_size > 20:
                        number_of_ind_to_show = 20
                    elif self.population_size > 9:
                        number_of_ind_to_show = 9
                    else:
                        raise ValueError('self.population_size cannot be less than 10')

                    for j in range(number_of_ind_to_show):
                        fittest_list.append(
                            [j + 1, self.population[j]['dna'], self.population[j]['fitness'],
                             self.population[j]['log']],
                        )
                    table.multi_value(fittest_list, with_headers=True, alignments=('left', 'left', 'right', 'left'))

                    # one person has to die and be replaced with the newborn baby
                    for baby in people:
                        random_index = randint(0, len(self.population) - 1)
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
                    if i != 0 and int(i * cores_num) % 50 == 0:
                        self.save_progress(i)

                    # store a take_snapshot of the fittest individuals of the population
                    if i != 0 and i % int(100 / cores_num) == 0:
                        self.take_snapshot(i * cores_num)

                    i += 1

        print('\n\n')
        print('Finished {} iterations.'.format(self.iterations))

        return self.population

    def run(self):
        return self.evolve()

    def save_progress(self, iterations_index):
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
            'session_id': self.session_id
        }

        with open(self.temp_path, 'wb') as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)

    def load_progress(self):
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
        self.session_id = data['session_id']

    def take_snapshot(self, index):
        """
        stores a snapshot of the fittest population members into a file.
        """
        path = './storage/genetics/{}.txt'.format(self.session_id)
        os.makedirs('./storage/genetics', exist_ok=True)
        txt = ''
        with open(path, 'a') as f:
            txt += '\n\n'
            txt += '# iteration {}'.format(index)
            txt += '\n'

            for i in range(30):
                txt += '\n'
                txt += "{} ==  {}  ==  {}  ==  {}".format(
                    i + 1, self.population[i]['dna'], self.population[i]['fitness'], self.population[i]['log']
                )

            f.write(txt)
