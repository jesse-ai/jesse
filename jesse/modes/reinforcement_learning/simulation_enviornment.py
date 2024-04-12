from typing import SupportsFloat, Any

import gymnasium as gym
import jesse.helpers as jh

from gymnasium import Space
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
    ) -> None:
        # jesse simulation variables
        self.candles: dict = candles
        self.length = simulation_minutes_length(candles)
        self.candles_step = 0
        self.candle_index = 0

        prepare_routes()

        # rl variables
        self.done = False
        self.observation = None
        self.strategy: Strategy = router.routes[0].strategy
        self.action_space: Space = self.strategy._actions_space()

    def reset(self, seed=None, options=None):
        # We need the following line to seed self.np_random
        super().reset(seed=seed)
        self.done = False
        prepare_times_before_simulation(self.candles)
        prepare_routes()
        # initiate candle store
        store.candles.init_storage(5000)

        if len(router.routes) != 1:
            raise ValueError("Jesse currently supports agent with only one route.")

        save_daily_portfolio_balance()
        self.candle_index = 0
        self.candles_step = calculate_minimum_candle_step()

        simulate_new_candles(self.candles, self.candle_index, self.candles_step)

        self.strategy = router.routes[0].strategy
        self._pre_action_execute()
        self.observation = self.strategy.env_observation()

        return self.observation

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
        self.strategy._post_action_execute()
        # now check to see if there's any MARKET orders waiting to be executed
        execute_market_orders()
        if self.candle_index != 0 and self.candle_index % 1440 == 0:
            save_daily_portfolio_balance()

        self.candle_index += self.candles_step
        simulate_new_candles(self.candles, self.candle_index, self.candles_step)

        self.observation = self.strategy.env_observation()
        return self.observation, self.strategy.reward(), self.done, False, {}

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
