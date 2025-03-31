from torch import nn

# Definition of the netwroks
class DQN(nn.Module):
    # Deep Q Network
    def __init__(self, obs_len, hidden_size, actions_n):
        super(DQN, self).__init__()
        # we might want Conv1d ?
        self.fc_val = nn.Sequential(
            nn.Linear(obs_len, hidden_size),
            nn.LeakyReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.LeakyReLU(),
            nn.Linear(hidden_size, actions_n)
        )

    def forward(self, x):
        h = self.fc_val(x)
        return h



class DuelingDQN(nn.Module):
    # Linear Dueling Deep Q Network
    def __init__(self, obs_len, hidden_size, actions_n):
        super(DuelingDQN, self).__init__()

        self.feauture_layer = nn.Sequential(
            nn.Linear(obs_len, hidden_size),
            nn.LeakyReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.LeakyReLU(),
        )

        self.value_stream = nn.Sequential(
            nn.Linear(hidden_size, hidden_size),
            nn.LeakyReLU(),
            nn.Linear(hidden_size, 1),
        )

        self.advantage_stream = nn.Sequential(
            nn.Linear(hidden_size, hidden_size),
            nn.LeakyReLU(),
            nn.Linear(hidden_size, actions_n)
        )

    def forward(self, state):
        features = self.feauture_layer(state)
        values = self.value_stream(features)
        advantages = self.advantage_stream(features)
        qvals = values + (advantages - advantages.mean())

        return qvals


# Convolutional DQN
class ConvDQN(nn.Module):
    def __init__(self, seq_len_in, actions_n, kernel_size=8):
        super(ConvDQN, self).__init__()
        n_filters = 64
        max_pool_kernel = 2
        self.conv1 = nn.Conv1d(1, n_filters, kernel_size)
        self.maxPool = nn.MaxPool1d(max_pool_kernel, stride=1)
        self.LRelu = nn.LeakyReLU()
        self.conv2 = nn.Conv1d(n_filters, n_filters, kernel_size // 2)

        self.hidden_dim = n_filters * ((((
                                                     seq_len_in - kernel_size + 1) - max_pool_kernel + 1) - kernel_size // 2 + 1) - max_pool_kernel + 1)

        self.out_layer = nn.Linear(self.hidden_dim, actions_n)

    def forward(self, x):
        c1_out = self.conv1(x)
        max_pool_1 = self.maxPool(self.LRelu(c1_out))
        c2_out = self.conv2(max_pool_1)
        max_pool_2 = self.maxPool(self.LRelu(c2_out))
        #    print("c1_out:\t%s"%str(c1_out.shape))
        #    print("max_pool_1:\t%s"%str(max_pool_1.shape))
        #    print("c2_out:\t%s"%str(c2_out.shape))
        #    print("max_pool_2:\t%s"%str(max_pool_2.shape))

        max_pool_2 = max_pool_2.view(-1, self.hidden_dim)
        #    print("max_pool_2_view:\t%s"%str(max_pool_2.shape))

        return self.LRelu(self.out_layer(max_pool_2))


# Convolutional Dueling DQN
class ConvDuelingDQN(nn.Module):
    def __init__(self, seq_len_in, actions_n, kernel_size=8):
        super(ConvDuelingDQN, self).__init__()
        n_filters = 64
        max_pool_kernel = 2
        self.conv1 = nn.Conv1d(1, n_filters, kernel_size)
        self.maxPool = nn.MaxPool1d(max_pool_kernel, stride=1)
        self.LRelu = nn.LeakyReLU()
        self.conv2 = nn.Conv1d(n_filters, n_filters, kernel_size // 2)
        self.hidden_dim = n_filters * ((((
                                                     seq_len_in - kernel_size + 1) - max_pool_kernel + 1) - kernel_size // 2 + 1) - max_pool_kernel + 1)
        paper_hidden_dim = 120
        self.split_layer = nn.Linear(self.hidden_dim, paper_hidden_dim)

        self.value_stream = nn.Sequential(
            nn.Linear(paper_hidden_dim, paper_hidden_dim),
            nn.LeakyReLU(),
            nn.Linear(paper_hidden_dim, 1),
        )

        self.advantage_stream = nn.Sequential(
            nn.Linear(paper_hidden_dim, paper_hidden_dim),
            nn.LeakyReLU(),
            nn.Linear(paper_hidden_dim, actions_n)
        )

    def forward(self, x):
        c1_out = self.conv1(x)
        max_pool_1 = self.maxPool(self.LRelu(c1_out))
        c2_out = self.conv2(max_pool_1)
        max_pool_2 = self.maxPool(self.LRelu(c2_out))
        # DEBUG code:
        #    print("c1_out:\t%s"%str(c1_out.shape))
        #    print("max_pool_1:\t%s"%str(max_pool_1.shape))
        #    print("c2_out:\t%s"%str(c2_out.shape))
        #    print("max_pool_2:\t%s"%str(max_pool_2.shape))

        max_pool_2 = max_pool_2.view(-1, self.hidden_dim)
        #    print("max_pool_2_view:\t%s"%str(max_pool_2.shape))

        split = self.split_layer(max_pool_2)
        values = self.value_stream(split)
        advantages = self.advantage_stream(split)
        qvals = values + (advantages - advantages.mean())
        return qvals
