from gymnasium import Space


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
