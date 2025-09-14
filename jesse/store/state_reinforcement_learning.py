import numpy as np
from typing import Any, Dict, Optional
from gymnasium import spaces


class ReinforcementLearningState:
    """
    Store for managing reinforcement learning state between strategy and environment
    """
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """Reset RL state"""
        self._current_action = None
        self._current_observation = None
        self._current_reward = 0.0
        self._is_done = False
        self._action_space = None
        self._observation_space = None
        self._step_count = 0
        self._episode_metrics = {}
    
    def set_action(self, action: Any):
        """Set current action from RL agent"""
        self._current_action = action
    
    def get_action(self) -> Any:
        """Get current action for strategy"""
        return self._current_action
    
    def set_observation(self, observation: np.ndarray):
        """Set current observation from strategy"""
        self._current_observation = observation
    
    def get_observation(self) -> Optional[np.ndarray]:
        """Get current observation for RL agent"""
        return self._current_observation
    
    def set_reward(self, reward: float):
        """Set current reward from strategy"""
        self._current_reward = reward
    
    def get_reward(self) -> float:
        """Get current reward for RL agent"""
        return self._current_reward
    
    def set_done(self, done: bool):
        """Set episode done flag"""
        self._is_done = done
    
    def is_done(self) -> bool:
        """Check if episode is done"""
        return self._is_done
    
    def set_action_space(self, action_space: spaces.Space):
        """Set action space from strategy"""
        self._action_space = action_space
    
    def get_action_space(self) -> Optional[spaces.Space]:
        """Get action space"""
        return self._action_space
    
    def set_observation_space(self, observation_space: spaces.Space):
        """Set observation space from strategy"""
        self._observation_space = observation_space
    
    def get_observation_space(self) -> Optional[spaces.Space]:
        """Get observation space"""
        return self._observation_space
    
    def increment_step(self):
        """Increment step counter"""
        self._step_count += 1
    
    def get_step_count(self) -> int:
        """Get current step count"""
        return self._step_count
    
    def set_metric(self, key: str, value: Any):
        """Set episode metric"""
        self._episode_metrics[key] = value
    
    def get_metric(self, key: str) -> Any:
        """Get episode metric"""
        return self._episode_metrics.get(key)
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all episode metrics"""
        return self._episode_metrics.copy()
    
    def has_action(self) -> bool:
        """Check if action is available"""
        return self._current_action is not None
    
    def clear_action(self):
        """Clear current action"""
        self._current_action = None
