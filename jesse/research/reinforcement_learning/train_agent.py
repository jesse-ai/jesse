from typing import Sequence

import joblib
from agilerl.algorithms.ppo import PPO

from jesse.research.reinforcement_learning.environment import (
    JesseGymSimulationEnvironment,
)
from jesse_tools.jesse_bulk import get_candles_with_cache  # type: ignore


import numpy as np
from agilerl.hpo.mutation import Mutations
from agilerl.hpo.tournament import TournamentSelection
from agilerl.utils.utils import (
    calculate_vectorized_scores,
    initialPopulation,
)
from tqdm import trange

import gymnasium as gym


def _get_init_hp(n_jobs: int) -> dict:
    # Initial hyperparameters
    return {
        "POP_SIZE": n_jobs,  # Population size
        "DISCRETE_ACTIONS": True,  # Discrete action space
        "BATCH_SIZE": 128,  # Batch size
        "LR": 0.001,  # Learning rate
        "GAMMA": 0.99,  # Discount factor
        "GAE_LAMBDA": 0.95,  # Lambda for general advantage estimation
        "ACTION_STD_INIT": 0.6,  # Initial action standard deviation
        "CLIP_COEF": 0.2,  # Surrogate clipping coefficient
        "ENT_COEF": 0.01,  # Entropy coefficient
        "VF_COEF": 0.5,  # Value function coefficient
        "MAX_GRAD_NORM": 0.5,  # Maximum norm for gradient clipping
        "TARGET_KL": None,  # Target KL divergence threshold
        "UPDATE_EPOCHS": 4,  # Number of policy update epochs
        # Swap image channels dimension from last to first [H, W, C] -> [C, H, W]
        "CHANNELS_LAST": False,  # Use with RGB states
        "EPISODES": 300,  # Number of episodes to train for
        "EVO_EPOCHS": 20,  # Evolution frequency, i.e. evolve after every 20 episodes
        "TARGET_SCORE": 200.0,  # Target score that will beat the environment
        "EVO_LOOP": 3,  # Number of evaluation episodes
        "MAX_STEPS": 500,  # Maximum number of steps an agent takes in an environment
        "TOURN_SIZE": 2,  # Tournament size
        "ELITISM": True,  # Elitism in tournament selection
    }


def _get_mutation_parameters() -> dict:
    return {
        # Mutation probabilities
        "NO_MUT": 0.4,  # No mutation
        "ARCH_MUT": 0.2,  # Architecture mutation
        "NEW_LAYER": 0.2,  # New layer mutation
        "PARAMS_MUT": 0.2,  # Network parameters mutation
        "ACT_MUT": 0.2,  # Activation layer mutation
        "RL_HP_MUT": 0.2,  # Learning HP mutation
        "RL_HP_SELECTION": ["lr", "batch_size"],  # Learning HPs to choose from
        "MUT_SD": 0.1,  # Mutation strength
        "RAND_SEED": 42,  # Random seed
        # Define max and min limits for mutating RL hyperparams
        "MIN_LR": 0.0001,
        "MAX_LR": 0.01,
        "MIN_BATCH_SIZE": 8,
        "MAX_BATCH_SIZE": 1024,
    }


def _create_pop(
    action_dim: int,
    state_dim: Sequence[int],
    one_hot: bool,
    device: str = "cpu",
    n_jobs: int = -1,
):
    INIT_HP = _get_init_hp(n_jobs)
    MUT_P = _get_mutation_parameters()
    # Define the network configuration of a simple mlp with two hidden layers, each with 64 nodes
    net_config = {"arch": "mlp", "hidden_size": [64, 64]}
    pop = initialPopulation(
        algo="PPO",  # Algorithm
        state_dim=state_dim,  # type: ignore
        action_dim=action_dim,  # Action dimension
        one_hot=one_hot,
        net_config=net_config,  # Network configuration
        INIT_HP=INIT_HP,
        population_size=INIT_HP["POP_SIZE"],
        device=device,
    )

    tournament = TournamentSelection(
        INIT_HP["TOURN_SIZE"],
        INIT_HP["ELITISM"],
        INIT_HP["POP_SIZE"],
        INIT_HP["EVO_EPOCHS"],
    )

    mutations = Mutations(
        algo="PPO",
        no_mutation=MUT_P["NO_MUT"],
        architecture=MUT_P["ARCH_MUT"],
        new_layer_prob=MUT_P["NEW_LAYER"],
        parameters=MUT_P["PARAMS_MUT"],
        activation=MUT_P["ACT_MUT"],
        rl_hp=MUT_P["RL_HP_MUT"],
        rl_hp_selection=MUT_P["RL_HP_SELECTION"],
        mutation_sd=MUT_P["MUT_SD"],
        arch=net_config["arch"],
        rand_seed=MUT_P["RAND_SEED"],
        device=device,
    )
    return pop, tournament, mutations


def _agent_play(
    agent: PPO, env: gym.vector.AsyncVectorEnv, minutes_per_episode: int
) -> tuple[tuple, int]:
    state = env.reset()[0]
    next_state = None  # next_step variable placeholder
    step = 0  # step variable placeholder

    states = []
    actions = []
    log_probs = []
    rewards = []
    dones = []
    values = []
    for step in range(minutes_per_episode):
        action, log_prob, _, value = agent.getAction(state)
        next_state, reward, done, _, _ = env.step(action)

        states.append(state)
        actions.append(action)
        log_probs.append(log_prob)
        rewards.append(reward)
        dones.append(done)
        values.append(value)

        state = next_state

    scores = calculate_vectorized_scores(
        np.array(rewards).transpose((1, 0)), np.array(dones).transpose((1, 0))
    )
    score = np.mean(scores)
    agent.scores.append(score)

    experiences = (
        states,
        actions,
        log_probs,
        rewards,
        dones,
        values,
        next_state,
    )
    return experiences, step


def train(
    candles: list[dict] | dict,
    routes: list[list[dict]] | list[dict],
    extra_routes: list[dict] | None = None,
    episodes=1000,
    minutes_per_episode=1000,
    n_jobs: int = -1,
) -> None:
    if n_jobs == -1:
        n_jobs = joblib.cpu_count()

    INIT_HP = _get_init_hp(n_jobs)

    if type(candles) is dict:
        candles = [candles]
    if type(routes[0]) is dict:
        routes = [routes]

    environments = [
        gym.vector.AsyncVectorEnv(
            [
                lambda: JesseGymSimulationEnvironment(
                    candles[i % len(candles)],
                    routes[i % len(candles)],
                    extra_routes,
                    minutes_per_episode,
                )
            ]
        )
        for i in range(n_jobs)
    ]
    action_dim = environments[0].action_space.shape[0]
    state_dim = environments[0].observation_space.shape  # Continuous observation space
    one_hot = False  # Does not require one-hot encoding

    pop, tournament, mutations = _create_pop(
        action_dim=action_dim,
        state_dim=state_dim,
        one_hot=one_hot,
        n_jobs=n_jobs,
    )
    elite = pop[0]  # elite variable placeholder

    parallel = joblib.Parallel(n_jobs, require="sharedmem")
    for episode in trange(episodes):
        agent_results = parallel(
            joblib.delayed(_agent_play)(agent, env, minutes_per_episode)
            for agent, env in zip(pop, environments)
        )
        for agent, (experiences, steps) in zip(pop, agent_results):
            # Learn according to agent's RL algorithm
            agent.learn(experiences)
            agent.steps[-1] += steps + 1

        # Now evolve population if necessary
        if (episode + 1) % INIT_HP["EVO_EPOCHS"] == 0:
            # Evaluate population
            fitnesses = parallel(
                joblib.delayed(agent.test)(
                    env,
                    swap_channels=INIT_HP["CHANNELS_LAST"],
                    max_steps=INIT_HP["MAX_STEPS"],
                    loop=INIT_HP["EVO_LOOP"],
                )
                for agent, env in zip(pop, environments)
            )

            fitness = ["%.2f" % fitness for fitness in fitnesses]
            avg_fitness = ["%.2f" % np.mean(agent.fitness[-100:]) for agent in pop]
            avg_score = ["%.2f" % np.mean(agent.scores[-100:]) for agent in pop]
            agents = [agent.index for agent in pop]
            num_steps = [agent.steps[-1] for agent in pop]
            muts = [agent.mut for agent in pop]

            print(
                f"""
                --- Epoch {episode + 1} ---
                Fitness:\t\t{fitness}
                100 fitness avgs:\t{avg_fitness}
                100 score avgs:\t{avg_score}
                Agents:\t\t{agents}
                Steps:\t\t{num_steps}
                Mutations:\t\t{muts}
                """,
                end="\r",
            )

            # Tournament selection and population mutation
            elite, pop = tournament.select(pop)
            pop = mutations.mutation(pop)


# =================
