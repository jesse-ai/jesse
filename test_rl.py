from stable_baselines3 import PPO
from rl_env import TradingEnv

# Load the trained model
model = PPO.load("ppo_trading_model")

# Initialize your custom trading environment
env = TradingEnv()

# Reset environment (Gym API >= 0.26+ returns a tuple)
obs, _ = env.reset()

# Initialize done flags
terminated = False
truncated = False

# Run the testing loop
while not (terminated or truncated):
    # Predict action from model (obs must be np.ndarray or dict)
    action, _ = model.predict(obs, deterministic=True)

    # Step the environment (Gym API >= 0.26)
    obs, reward, terminated, truncated, _ = env.step(action)

    # Optional: render to visualize
    env.render()
