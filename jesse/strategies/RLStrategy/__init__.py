# jesse/strategies/RLStrategy.py
import torch
from jesse.strategies import Strategy
from jesse.rl.Agent import Agent  # Импорт RL-агента
import jesse.indicators as ta

class RLStrategy(Strategy):
    def __init__(self):
        super().__init__()
        self.agent = Agent(...)  # Инициализация RL-агента

    def should_long(self) -> bool:
        action = self.agent.select_action(self.get_state())  # Получение действия от RL-агента
        if action == 1:  # Если действие - "покупать"
            return True
        return False

    def should_short(self) -> bool:
        action = self.agent.select_action(self.get_state())  # Получение действия от RL-агента
        if action == 2:  # Если действие - "продавать"
            return True
        return False

    def go_long(self):
        qty = self.available_margin * 0.99
        self.buy = qty, self.price

    def go_short(self):
        qty = self.available_margin * 0.99
        self.sell = qty, self.price

    def should_cancel(self):
        return False

    def get_state(self):
        # Получение состояния рынка
        # Пример: использование последних значений цены, объема и RSI
        close = self.candles[:, 2]
        volume = self.candles[:, 5]
        rsi = ta.rsi(close, period=14)

        # Создание тензора PyTorch
        state = torch.tensor([close[-1], volume[-1], rsi[-1]])
        return state