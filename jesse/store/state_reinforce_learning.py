import numpy as np
from agilerl.utils.utils import calculate_vectorized_scores


class ReinforceLearningState:

    def __init__(self):
        self.states = []
        self.actions = []
        self.log_probs = []
        self.rewards = []
        self.values = []

    def scores(self):
        return calculate_vectorized_scores(
            np.array(self.rewards).transpose((1, 0)), np.zeros((len(self.rewards), 1))
        )

    def experience(self):
        dones = np.zeros((len(self.rewards), 1))
        return (
            self.states[:-1],
            self.actions[:-1],
            self.log_probs[:-1],
            self.rewards[:-1],
            dones[:-1],
            self.values[:-1],
            self.states[-1],
        )
