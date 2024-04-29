import random
from typing import SupportsFloat, Any

import gymnasium as gym
import jesse.helpers as jh

from gymnasium import Space, spaces
from gymnasium.core import ActType, ObsType

from jesse.modes.backtest_mode import (
    prepare_times_before_simulation,
    prepare_routes,
    calculate_minimum_candle_step,
    simulate_new_candles,
    execute_market_orders,
)
from jesse.services.candle import inject_warmup_candles_to_store
from jesse.store import store
from jesse.routes import router
from jesse.config import config
from jesse.enums import timeframes
from jesse.strategies import Strategy
from jesse.modes.utils import save_daily_portfolio_balance


class JesseGymSimulationEnvironment(gym.Env):

    def __init__(
        self,
        candles: dict,
        route: dict,
        extra_routes: list[dict] | None = None,
        candles_per_episode: int = -1,
        num_warmup_candles: int = 0,
    ) -> None:
        config["app"]["trading_mode"] = "backtest"

        # jesse simulation variables
        self.candles: dict = candles
        self.route: dict = route
        self.extra_routes = extra_routes or []
        self.candles_step = 0
        self.candle_index = 0
        self.num_warmup_candles = num_warmup_candles
        self.timeframe_in_minutes = jh.timeframe_to_one_minutes(self.route["timeframe"])
        self.candles_per_episode = candles_per_episode
        self.episode_candles = self.candles
        self.episode_warmup_candles = {}

        router.initiate([route], extra_routes)
        prepare_routes()

        # rl variables
        self.done = False
        self.observation = None
        self.strategy: Strategy = router.routes[0].strategy
        self.action_space: spaces.Discrete = self.strategy._actions_space()
        self.observation_space: Space = self.strategy.env_space()

    def reset(self, *, seed=None, options: dict | None = None):
        super().reset(seed=seed, options=options)
        options = options or {}
        self.candles = options.get("candles", None) or self.candles
        self.route = options.get("route", None) or self.route
        self.extra_routes = options.get("extra_routes", None) or self.extra_routes
        self.candles_per_episode = (
            options.get("candles_per_episode", None) or self.candles_per_episode
        )
        self.done = False
        self._prepare_candles_for_episode()
        router.initiate([self.route], self.extra_routes)
        prepare_times_before_simulation(self.episode_candles)
        prepare_routes()
        self._initiate_candles()

        if len(router.routes) != 1:
            raise ValueError("Jesse currently supports agent with only one route.")

        save_daily_portfolio_balance()
        self.candle_index = 0
        self.candles_step = calculate_minimum_candle_step()

        simulate_new_candles(self.episode_candles, self.candle_index, self.candles_step)

        self.strategy = router.routes[0].strategy
        self._pre_action_execute()
        self.observation = self.strategy.env_observation()

        return self.observation, {}

    def step(
        self, action: ActType
    ) -> tuple[ObsType, SupportsFloat, bool, bool, dict[str, Any]]:
        if self.done:
            raise ValueError(
                "Environment should be reset! the simulation has already finished."
            )

        # inject action to the strategy!
        self.strategy._inject_agent_action(action)

        self._post_action_execute()
        # now check to see if there's any MARKET orders waiting to be executed
        execute_market_orders()
        if self.candle_index != 0 and self.candle_index % 1440 == 0:
            save_daily_portfolio_balance()

        if (
            self.strategy.index * self.timeframe_in_minutes
            == self.simulation_minutes_length
        ):
            self.done = True
            self.strategy._terminate()
            return self.observation, self.strategy.reward(), self.done, False, {}

        self.candle_index += self.candles_step
        simulate_new_candles(self.episode_candles, self.candle_index, self.candles_step)

        self._pre_action_execute()
        self.observation = self.strategy.env_observation()
        return self.observation, self.strategy.reward(), self.done, False, {}

    @property
    def simulation_minutes_length(self):
        return self.candles_per_episode * self.timeframe_in_minutes

    def _prepare_candles_for_episode(self):
        max_candles_length = len(list(self.candles.values())[0]['candles']) // self.timeframe_in_minutes
        if self.simulation_minutes_length == -1:
            self.candles_per_episode = max_candles_length
            starting_point = self.num_warmup_candles
            warmup_candles = 0
        else:
            self.candles_per_episode = min(
                self.simulation_minutes_length // self.timeframe_in_minutes,
                max_candles_length,
            )
            starting_point = random.randint(
                self.num_warmup_candles,
                (max_candles_length - self.candles_per_episode),
            )
            warmup_candles = starting_point - self.num_warmup_candles
            warmup_candles *= self.timeframe_in_minutes

        starting_point *= self.timeframe_in_minutes
        self.episode_candles = {
            candles_key: {
                "exchange": candles_values["exchange"],
                "symbol": candles_values["symbol"],
                "candles": candles_values["candles"][
                    starting_point : starting_point + self.simulation_minutes_length
                ],
            }
            for candles_key, candles_values in self.candles.items()
        }

        self.episode_warmup_candles = {
            candles_key: {
                "exchange": candles_values["exchange"],
                "symbol": candles_values["symbol"],
                "candles": candles_values["candles"][
                    starting_point - warmup_candles : starting_point
                ],
            }
            for candles_key, candles_values in self.candles.items()
        }

    def _initiate_candles(self):
        store.candles.init_storage(5000)
        if self.num_warmup_candles:
            routes = [self.route] + self.extra_routes
            injected_routes = set([])
            for route in routes:
                key = jh.key(route["exchange"], route["symbol"])
                if key in injected_routes:
                    continue
                injected_routes.add(key)
                # inject warm-up candles
                inject_warmup_candles_to_store(
                    self.episode_warmup_candles[key]["candles"],
                    route["exchange"],
                    route["symbol"],
                )

    def _pre_action_execute(self):
        count = jh.timeframe_to_one_minutes(self.strategy.timeframe)
        # 1m timeframe
        if self.strategy.timeframe == timeframes.MINUTE_1:
            self.strategy._pre_action_execute()
        elif (self.candle_index + self.candles_step) % count == 0:
            # print candle
            self.strategy._pre_action_execute()

    def _post_action_execute(self):
        count = jh.timeframe_to_one_minutes(self.strategy.timeframe)
        # 1m timeframe
        if self.strategy.timeframe == timeframes.MINUTE_1:
            self.strategy._post_action_execute()
        elif (self.candle_index + self.candles_step) % count == 0:
            # print candle
            self.strategy._post_action_execute()
