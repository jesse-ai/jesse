# tests/test_rl_strategy.py
import unittest
from jesse.strategies.RLStrategy import RLStrategy  # Импорт RL-стратегии
from jesse.rl.Agent import Agent
import jesse.helpers as jh
from jesse.enums import timeframes, exchanges
from jesse.factories import range_candles
from jesse.modes import backtest_mode
from jesse.routes import router
from jesse.store import store
from jesse.config import config


class TestRLStrategy(unittest.TestCase):
    def test_rl_strategy(self):
        # Создание фиктивных данных
        candles = {
            jh.key(exchanges.SANDBOX, 'BTC-USDT'): {
                'exchange': exchanges.SANDBOX,
                'symbol': 'BTC-USDT',
                'candles': range_candles(5 * 20)
            }
        }

        # Определение маршрутов
        routes = [
            {'symbol': 'BTC-USDT', 'timeframe': timeframes.MINUTE_5, 'strategy': 'RLStrategy'}
        ]

        config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'futures'

        # Запуск backtest_mode
        backtest_mode.run('000', False, {}, exchanges.SANDBOX, routes, [], '2019-04-01', '2019-04-02', candles)

        # Проверка результатов
        # assert ...


        # Проверяем, что стратегия была создана и запущена
        self.assertIsNotNone(router.routes[0].strategy)
        self.assertIsInstance(router.routes[0].strategy, RLStrategy)
        
        # Проверяем, что агент был инициализирован
        self.assertIsNotNone(router.routes[0].strategy.agent)
        self.assertIsInstance(router.routes[0].strategy.agent, Agent)
        
        # Дополнительные проверки могут включать:
        # - проверку состояния агента
        # - проверку, что агент может получать состояние из окружения
        # - проверку, что агент может выбирать действия




rl = RLStrategy()

