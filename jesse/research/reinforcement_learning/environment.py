import random
from typing import SupportsFloat, Any

import gymnasium as gym
import jesse.helpers as jh

from gymnasium import Space, spaces
from gymnasium.core import ActType, ObsType

from jesse.modes.backtest_mode import (
    simulation_minutes_length,
    prepare_times_before_simulation,
    prepare_routes,
    calculate_minimum_candle_step,
    simulate_new_candles,
    execute_market_orders,
)
from jesse.store import store
from jesse.routes import router
from jesse.enums import timeframes
from jesse.strategies import Strategy
from jesse.modes.utils import save_daily_portfolio_balance


class JesseGymSimulationEnvironment(gym.Env):

    def __init__(
        self,
        candles: dict,
        routes: list[dict],
        extra_routes: list[dict] | None = None,
        minutes_per_episode: int = -1,
    ) -> None:
        # jesse simulation variables
        router.initiate(routes, extra_routes)
        self.candles: dict = candles
        self.routes: list[dict] = routes
        self.extra_routes = extra_routes or []
        self.simulation_minutes_length = minutes_per_episode
        self.candles_step = 0
        self.candle_index = 0
        self.timeframe_in_minutes = jh.timeframe_to_one_minutes(
            self.routes[0]["timeframe"]
        )
        self.episode_candles = self.candles

        self._validations()
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
        self.routes = options.get("routes", None) or self.routes
        self.extra_routes = options.get("extra_routes", None) or self.extra_routes
        self.simulation_minutes_length = (
            options.get("minutes_per_episode", None) or self.simulation_minutes_length
        )
        self.done = False
        self._prepare_candles_for_episode()
        router.initiate(self.routes, self.extra_routes)
        prepare_times_before_simulation(self.episode_candles)
        prepare_routes()
        store.candles.init_storage(5000)

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

        if self.strategy.index * self.timeframe_in_minutes == self.simulation_minutes_length:
            self.done = True
            return self.observation, self.strategy.reward(), self.done, False, {}

        self.candle_index += self.candles_step
        simulate_new_candles(self.episode_candles, self.candle_index, self.candles_step)

        self._pre_action_execute()
        self.observation = self.strategy.env_observation()
        return self.observation, self.strategy.reward(), self.done, False, {}

    def _prepare_candles_for_episode(self):
        max_simulation_length = simulation_minutes_length(self.candles)
        if self.simulation_minutes_length == -1:
            self.simulation_minutes_length = max_simulation_length
            starting_point = 0
        else:
            self.simulation_minutes_length = min(
                self.simulation_minutes_length,
                max_simulation_length,
            )
            starting_point = random.randint(
                0,
                (max_simulation_length - self.simulation_minutes_length)
                // self.timeframe_in_minutes,
            )
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

    def _validations(self):
        if self.simulation_minutes_length > 0:
            timeframe = self.routes[0]["timeframe"]
            reminder = self.simulation_minutes_length % self.timeframe_in_minutes
            if reminder != 0:
                raise ValueError(
                    f"minutes_per_episode have to be divided by {timeframe}, What about "
                    f"{self.simulation_minutes_length + self.timeframe_in_minutes - reminder} instead of "
                    f"{self.simulation_minutes_length} for minutes_per_episode"
                )
