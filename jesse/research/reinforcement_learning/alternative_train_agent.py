import os
import random
import time
from typing import Sequence

import joblib
import numpy as np
import torch
from agilerl.algorithms.ppo import PPO
from agilerl.hpo.mutation import Mutations
from agilerl.hpo.tournament import TournamentSelection
from agilerl.utils.utils import initialPopulation
from tqdm import trange

import jesse.helpers as jh

from pydantic import BaseModel

from jesse.research import backtest
from jesse.research.reinforcement_learning.agent_settings import AgentSettings


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
        initialPopulation(
            algo="PPO",  # Algorithm
            state_dim=state_dim,  # type: ignore
            action_dim=action_dim,  # Action dimension
            one_hot=one_hot,
            net_config=net_config,  # Network configuration
            INIT_HP=INIT_HP,
            population_size=max(0, INIT_HP["POP_SIZE"] - len(load_agents)),
            device=device,
        )
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
        evaluation_fitness = []
        for agent in [pop[0]]:
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

            if (episode + 1) % INIT_HP["EVO_EPOCHS"] == 0:
                evaluation_fitness.append(np.mean(result["experience"][3]))

        if (episode + 1) % INIT_HP["EVO_EPOCHS"] == 0:
            fitness = ["%.2f" % fitness for fitness in evaluation_fitness]
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

            # Save the trained algorithm
            saved_agent = save_path.format(
                strategy=train_configs[0].route["strategy"],
                i=episode + 1,
                ts=int(time.time()),
            )
            elite.saveCheckpoint(saved_agent)
