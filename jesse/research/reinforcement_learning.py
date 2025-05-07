import os
import time
import torch
import random

import numpy as np
import jesse.helpers as jh

from tqdm import trange
from typing import Sequence
from gymnasium import Space
from pydantic import BaseModel
from jesse.research import backtest
from agilerl.algorithms.ppo import PPO
from agilerl.hpo.mutation import Mutations
from agilerl.hpo.tournament import TournamentSelection
# from agilerl.utils.algo_utils import initialPopulation




class AgentSettings:

    def __init__(
        self,
        actions_space: list,
        env_space: Space,
        agent_path: str | list[str] | None = None,
        initial_hp: dict | None = None,
        initial_mut: dict | None = None,
        net_config: dict | None = None,
    ):
        self.agent_path = agent_path
        self.env_space = env_space
        self.actions_space = actions_space

        initial_hp = initial_hp or {}
        initial_mut = initial_mut or {}
        if net_config is None:
            net_config = {
                "arch": "mlp",
                "hidden_size": [64],
            }
        self.net_config: dict = net_config

        self.initial_hp: dict = {
            "POP_SIZE": 4,  # Population size
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
        } | initial_hp
        self.mutation_parameters: dict = {
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
        } | initial_mut


class AgentTrainingConfig(BaseModel):
    candles: dict
    route: dict
    extra_routes: list[dict] = []
    starting_balance: int = 10_000
    fee_rate: float = 0.002
    futures_leverage: int = 1


def _create_pop(
    agent_settings: AgentSettings,
    action_dim: int,
    state_dim: Sequence[int],
    one_hot: bool,
):
    device = "cuda" if torch.cuda.is_available() else "cpu"

    INIT_HP = agent_settings.initial_hp
    MUT_P = agent_settings.mutation_parameters
    # Define the network configuration of a simple mlp with two hidden layers, each with 64 nodes
    net_config = agent_settings.net_config

    if isinstance(agent_settings.agent_path, str):
        load_agents = [PPO.load(agent_settings.agent_path, device=device)]
    elif isinstance(agent_settings.agent_path, list):
        load_agents = [
            PPO.load(path, device=device) for path in agent_settings.agent_path
        ]
    else:
        load_agents = []
    pop = (
        # initialPopulation(
        #     algo="PPO",  # Algorithm
        #     state_dim=state_dim,  # type: ignore
        #     action_dim=action_dim,  # Action dimension
        #     one_hot=one_hot,
        #     net_config=net_config,  # Network configuration
        #     INIT_HP=INIT_HP,
        #     population_size=max(0, INIT_HP["POP_SIZE"] - len(load_agents)),
        #     device=device,
        # )
        + load_agents
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


def _prepare_candles_for_episode(
    full_length_candles: dict,
    timeframe_in_minutes: int,
    candles_per_episode: int,
    num_warmup_candles: int,
):
    max_candles_length = (
        len(list(full_length_candles.values())[0]["candles"]) // timeframe_in_minutes
    )
    if candles_per_episode == -1:
        candles_per_episode = max_candles_length
        starting_point = num_warmup_candles
        warmup_candles = 0
    else:
        candles_per_episode = min(
            candles_per_episode,
            max_candles_length,
        )
        starting_point = random.randint(
            num_warmup_candles,
            (max_candles_length - candles_per_episode),
        )
        warmup_candles = starting_point - num_warmup_candles
        warmup_candles *= timeframe_in_minutes

    starting_point *= timeframe_in_minutes
    episode_candles = {
        candles_key: {
            "exchange": candles_values["exchange"],
            "symbol": candles_values["symbol"],
            "candles": candles_values["candles"][
                starting_point : starting_point
                + candles_per_episode * timeframe_in_minutes
            ],
        }
        for candles_key, candles_values in full_length_candles.items()
    }

    episode_warmup_candles = {
        candles_key: {
            "exchange": candles_values["exchange"],
            "symbol": candles_values["symbol"],
            "candles": candles_values["candles"][warmup_candles:starting_point],
        }
        for candles_key, candles_values in full_length_candles.items()
    }
    return episode_warmup_candles, episode_candles


def train(
    train_configs: list[AgentTrainingConfig],
    episodes=1000,
    candles_per_episode=1000,
    num_warmup_candles=3000,
    n_jobs: int = -1,
) -> None:
    strategy = jh.get_strategy_class(train_configs[0].route["strategy"])()
    agent_settings: AgentSettings = strategy.agent_settings()
    INIT_HP = agent_settings.initial_hp
    pop, tournament, mutations = _create_pop(
        agent_settings=agent_settings,
        action_dim=len(agent_settings.actions_space),
        state_dim=agent_settings.env_space.shape,
        one_hot=False,
    )
    save_path = "storage/agents/{strategy}-generation-{ts}-{i}"
    os.makedirs("storage/agents", exist_ok=True)
    for episode in trange(episodes):
        evaluation_fitness = [[] for _ in range(len(pop))]
        for i, agent in enumerate(pop):
            train_config_index = random.randint(0, len(train_configs) - 1)
            train_config = train_configs[train_config_index]
            warmup_candles, trading_candles = _prepare_candles_for_episode(
                full_length_candles=train_config.candles,
                timeframe_in_minutes=jh.timeframe_to_one_minutes(
                    train_config.route["timeframe"]
                ),
                candles_per_episode=candles_per_episode,
                num_warmup_candles=num_warmup_candles,
            )
            config = {
                "starting_balance": train_config.starting_balance,
                "fee": train_config.fee_rate,
                "type": "futures",
                "futures_leverage": train_config.futures_leverage,
                "futures_leverage_mode": "cross",
                "exchange": train_config.route["exchange"],
                "warm_up_candles": num_warmup_candles,
            }
            # Execute backtest
            result = backtest(
                config,
                [train_config.route],
                [],
                candles=trading_candles,
                warmup_candles=warmup_candles,
                fast_mode=True,
                agent=agent,
            )
            agent.scores.append(np.mean(result["scores"]))
            agent.learn(result["experience"])
            agent.steps[-1] += candles_per_episode

            evaluation_fitness[i].append(np.array(result["experience"][3]).T[0].mean())

        if (episode + 1) % INIT_HP["EVO_EPOCHS"] == 0:
            fitness = ["%.2f" % np.mean(fitness) for fitness in evaluation_fitness]
            avg_score = ["%.2f" % np.mean(agent.scores[-100:]) for agent in pop]
            agents = [agent.index for agent in pop]
            num_steps = [agent.steps[-1] for agent in pop]
            muts = [agent.mut for agent in pop]

            print(
                f"""
                --- Epoch {episode + 1} ---
                Fitness:\t\t{fitness}
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

            # Save the trained algorithm
            saved_agent = save_path.format(
                strategy=train_configs[0].route["strategy"],
                i=episode + 1,
                ts=int(time.time()),
            )
            elite.saveCheckpoint(saved_agent)
