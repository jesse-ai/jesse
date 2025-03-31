import torch
import torch.optim as optim
import torch.nn.functional as F
from jesse.rl.models import ConvDQN, ConvDuelingDQN
from jesse.rl.utils import ReplayMemory
from jesse.rl.utils import Transition
import random
from tqdm import tqdm
import re
import os


class Agent:
    """Definition of the Agent that will interact with the environment.

    Attributes:
        REPLAY_MEM_SIZE (:obj:`int`): max capacity of Replay Memory

        BATCH_SIZE (:obj:`int`): Batch size. Default is 40 as specified in the paper.

        GAMMA (:obj:`float`): The discount, should be a constant between 0 and 1
            that ensures the sum converges. It also controls the importance of future
            expected reward.

        EPS_START(:obj:`float`): initial value for epsilon of the e-greedy action
            selection

        EPS_END(:obj:`float`): final value for epsilon of the e-greedy action
            selection

        LEARNING_RATE(:obj:`float`): learning rate of the optimizer
            (Adam)

        INPUT_DIM (:obj:`int`): input dimentionality withut considering batch size.

        HIDDEN_DIM (:obj:`int`): hidden layer dimentionality (for Linear models only)

        ACTION_NUMBER (:obj:`int`): dimentionality of output layer of the Q network

        TARGET_UPDATE (:obj:`int`): period of Q target network updates

        MODEL (:obj:`string`): type of the model.

        DOUBLE (:obj:`bool`): Type of Q function computation.
    """

    def __init__(self,
                 REPLAY_MEM_SIZE=10000,
                 BATCH_SIZE=40,
                 GAMMA=0.98,
                 EPS_START=1,
                 EPS_END=0.12,
                 EPS_STEPS=300,
                 LEARNING_RATE=0.001,
                 INPUT_DIM=24,
                 HIDDEN_DIM=120,
                 ACTION_NUMBER=3,
                 TARGET_UPDATE=10,
                 MODEL='ddqn',
                 DOUBLE=True):

        self.REPLAY_MEM_SIZE = REPLAY_MEM_SIZE
        self.BATCH_SIZE = BATCH_SIZE
        self.GAMMA = GAMMA
        self.EPS_START = EPS_START
        self.EPS_END = EPS_END
        self.EPS_STEPS = EPS_STEPS
        self.LEARNING_RATE = LEARNING_RATE
        self.INPUT_DIM = INPUT_DIM
        self.HIDDEN_DIM = HIDDEN_DIM
        self.ACTION_NUMBER = ACTION_NUMBER
        self.TARGET_UPDATE = TARGET_UPDATE
        self.MODEL = MODEL  # deep q network (dqn) or Dueling deep q network (ddqn)
        self.DOUBLE = DOUBLE  # to understand if use or do not use a 'Double' model (regularization)
        self.TRAINING = True  # to do not pick random actions during testing
        if torch.backends.mps.is_available():
            # self.device = torch.device("mps")
            self.device = torch.device("cpu")
        else:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print("Agent is using device:\t" + str(self.device))
        
        '''elif self.MODEL == 'lin_ddqn':
            self.policy_net = DuelingDQN(self.INPUT_DIM, self.HIDDEN_DIM, self.ACTION_NUMBER).to(self.device)
            self.target_net = DuelingDQN(self.INPUT_DIM, self.HIDDEN_DIM, self.ACTION_NUMBER).to(self.device)
        elif self.MODEL == 'lin_dqn':
            self.policy_net = DQN(self.INPUT_DIM, self.HIDDEN_DIM, self.ACTION_NUMBER).to(self.device)
            self.target_net = DQN(self.INPUT_DIM, self.HIDDEN_DIM, self.ACTION_NUMBER).to(self.device)
        '''

        if self.MODEL == 'ddqn':
            self.policy_net = ConvDuelingDQN(self.INPUT_DIM, self.ACTION_NUMBER).to(self.device)
            self.target_net = ConvDuelingDQN(self.INPUT_DIM, self.ACTION_NUMBER).to(self.device)
        elif self.MODEL == 'dqn':
            self.policy_net = ConvDQN(self.INPUT_DIM, self.ACTION_NUMBER).to(self.device)
            self.target_net = ConvDQN(self.INPUT_DIM, self.ACTION_NUMBER).to(self.device)

        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()

        self.optimizer = optim.Adam(self.policy_net.parameters(), lr=self.LEARNING_RATE)
        self.memory = ReplayMemory(self.REPLAY_MEM_SIZE)
        self.steps_done = 0
        self.training_cumulative_reward = []

    def select_action(self, state):
        """ the epsilon-greedy action selection"""
        state = state.unsqueeze(0).unsqueeze(1)
        sample = random.random()
        if self.TRAINING:
            if self.steps_done > self.EPS_STEPS:
                eps_threshold = self.EPS_END
            else:
                eps_threshold = self.EPS_START
        else:
            eps_threshold = self.EPS_END

        self.steps_done += 1
        # [Exploitation] pick the best action according to current Q approx.
        if sample > eps_threshold:
            with torch.no_grad():
                # Return the number of the action with highest non normalized probability
                # TODO: decide if diverge from paper and normalize probabilities with
                # softmax or at least compare the architectures
                return torch.tensor([self.policy_net(state).argmax()], device=self.device, dtype=torch.long)

        # [Exploration]  pick a random action from the action space
        else:
            return torch.tensor([random.randrange(self.ACTION_NUMBER)], device=self.device, dtype=torch.long)

    def optimize_model(self):
        if len(self.memory) < self.BATCH_SIZE:
            # it will return without doing nothing if we have not enough data to sample
            return
        transitions = self.memory.sample(self.BATCH_SIZE)
        # Transpose the batch (see https://stackoverflow.com/a/19343/3343043 for
        # detailed explanation). This converts batch-array of Transitions
        # to Transition of batch-arrays.
        # Transition is the named tuple defined above.
        batch = Transition(*zip(*transitions))

        # Compute a mask of non-final states and concatenate the batch elements
        # (a final state would've been the one after which simulation ended)
        #
        # non_final_mask is a column vector telling wich state of the sampled is final
        # non_final_next_states contains all the non-final states sampled
        non_final_mask = torch.tensor(tuple(map(lambda s: s is not None, batch.next_state)), device=self.device,
                                      dtype=torch.bool)
        nfns = [s for s in batch.next_state if s is not None]
        non_final_next_states = torch.cat(nfns).view(len(nfns), -1)
        non_final_next_states = non_final_next_states.unsqueeze(1)

        state_batch = torch.cat(batch.state).view(self.BATCH_SIZE, -1)
        state_batch = state_batch.unsqueeze(1)
        action_batch = torch.cat(batch.action).view(self.BATCH_SIZE, -1)
        reward_batch = torch.cat(batch.reward).view(self.BATCH_SIZE, -1)

        # Compute Q(s_t, a) - the model computes Q(s_t), then we select the
        # columns of actions taken. These are the actions which would've been taken
        # for each batch state according to policy_net
        state_action_values = self.policy_net(state_batch).gather(1, action_batch)

        # Compute V(s_{t+1}) for all next states.
        # Expected values of actions for non_final_next_states are computed based
        # on the "older" target_net; selecting their best reward with max(1)[0].
        # This is merged based on the mask, such that we'll have either the expected
        # state value or 0 in case the state was final.
        # detach removes the tensor from the graph -> no gradient computation is
        # required
        next_state_values = torch.zeros(self.BATCH_SIZE, device=self.device)
        next_state_values[non_final_mask] = self.target_net(non_final_next_states).max(1)[0].detach()
        next_state_values = next_state_values.view(self.BATCH_SIZE, -1)

        # Compute the expected Q values
        expected_state_action_values = (next_state_values * self.GAMMA) + reward_batch
        # print("expected_state_action_values.shape:\t%s"%str(expected_state_action_values.shape))

        # Compute MSE loss
        loss = F.mse_loss(state_action_values,
                          expected_state_action_values)  # expected_state_action_values.unsqueeze(1)

        # Optimize the model
        self.optimizer.zero_grad()
        loss.backward()
        for param in self.policy_net.parameters():
            param.grad.data.clamp_(-1, 1)
        self.optimizer.step()

    def optimize_double_dqn_model(self):
        if len(self.memory) < self.BATCH_SIZE:
            # it will return without doing nothing if we have not enough data to sample
            return
        transitions = self.memory.sample(self.BATCH_SIZE)
        # Transpose the batch (see https://stackoverflow.com/a/19343/3343043 for
        # detailed explanation). This converts batch-array of Transitions
        # to Transition of batch-arrays.
        # Transition is the named tuple defined above.
        batch = Transition(*zip(*transitions))

        # Compute a mask of non-final states and concatenate the batch elements
        # (a final state would've been the one after which simulation ended)
        #
        # non_final_mask is a column vector telling wich state of the sampled is final
        # non_final_next_states contains all the non-final states sampled
        non_final_mask = torch.tensor(tuple(map(lambda s: s is not None, batch.next_state)), device=self.device,
                                      dtype=torch.bool)
        nfns = [s for s in batch.next_state if s is not None]
        non_final_next_states = torch.cat(nfns).view(len(nfns), -1)
        non_final_next_states = non_final_next_states.unsqueeze(1)

        state_batch = torch.cat(batch.state).view(self.BATCH_SIZE, -1)
        state_batch = state_batch.unsqueeze(1)
        action_batch = torch.cat(batch.action).view(self.BATCH_SIZE, -1)
        reward_batch = torch.cat(batch.reward).view(self.BATCH_SIZE, -1)
        # print("state_batch shape: %s\nstate_batch[0]:%s\nactionbatch shape: %s\nreward_batch shape: %s"%(str(state_batch.view(40,-1).shape),str(state_batch.view(40,-1)[0]),str(action_batch.shape),str(reward_batch.shape)))

        # Compute Q(s_t, a) - the model computes Q(s_t), then we select the
        # columns of actions taken. These are the actions which would've been taken
        # for each batch state according to policy_net
        state_action_values = self.policy_net(state_batch).gather(1, action_batch)

        # ---------- D-DQN Extra Line---------------
        _, next_state_action = self.policy_net(state_batch).max(1, keepdim=True)

        # Compute V(s_{t+1}) for all next states.
        # Expected values of actions for non_final_next_states are computed based
        # on the actions given by policynet.
        # This is merged based on the mask, such that we'll have either the expected
        # state value or 0 in case the state was final.
        # detach removes the tensor from the graph -> no gradient computation is
        # required
        next_state_values = torch.zeros(self.BATCH_SIZE, device=self.device).view(self.BATCH_SIZE, -1)

        out = self.target_net(non_final_next_states)
        next_state_values[non_final_mask] = out.gather(1, next_state_action[non_final_mask])
        # next_state_values = next_state_values.view(self.BATCH_SIZE, -1)
        # Compute the expected Q values
        expected_state_action_values = (next_state_values * self.GAMMA) + reward_batch

        # Compute MSE loss
        loss = F.mse_loss(state_action_values, expected_state_action_values)

        # Optimize the model
        self.optimizer.zero_grad()
        loss.backward()
        for param in self.policy_net.parameters():
            param.grad.data.clamp_(-1, 1)
        self.optimizer.step()

    def train(self, env, path, num_episodes=40):
        self.TRAINING = True
        cumulative_reward = [0 for t in range(num_episodes)]
        print("Training:")
        for i_episode in tqdm(range(num_episodes)):
            # Initialize the environment and state
            env.reset()  # reset the env st it is set at the beginning of the time serie
            self.steps_done = 0
            state = env.get_state()
            for t in range(len(env.data)):  # while not env.done

                # Select and perform an action
                action = self.select_action(state)
                reward, done, _ = env.step(action)

                cumulative_reward[i_episode] += reward.item()

                # Observe new state: it will be None if env.done = True. It is the next
                # state since env.step() has been called two rows above.
                next_state = env.get_state()

                # Store the transition in memory
                self.memory.push(state, action, next_state, reward)

                # Move to the next state
                state = next_state

                # Perform one step of the optimization (on the policy network): note that
                # it will return without doing nothing if we have not enough data to sample

                if self.DOUBLE:
                    self.optimize_double_dqn_model()
                else:
                    self.optimize_model()

                if done:
                    break

            # Update the target network, copying all weights and biases of policy_net
            if i_episode % self.TARGET_UPDATE == 0:
                self.target_net.load_state_dict(self.policy_net.state_dict())

        # save the model
        if self.DOUBLE:
            model_name = env.reward_f + '_reward_double_' + self.MODEL + '_model'
            count = 0
            while os.path.exists(path + model_name):  # avoid overrinding models
                count += 1
                model_name = model_name + "_" + str(count)

        else:
            model_name = env.reward_f + '_reward_' + self.MODEL + '_model'
            count = 0
            while os.path.exists(path + model_name):  # avoid overrinding models
                count += 1
                model_name = model_name + "_" + str(count)

        torch.save(self.policy_net.state_dict(), path + model_name)

        return cumulative_reward

    def test(self, env_test, model_name=None, path=None):
        self.TRAINING = False
        cumulative_reward = [0 for t in range(len(env_test.data))]
        reward_list = [0 for t in range(len(env_test.data))]

        if model_name is None:
            pass
        elif path is not None:
            if re.match(".*_dqn_.*", model_name):
                self.policy_net = ConvDQN(self.INPUT_DIM, self.ACTION_NUMBER).to(self.device)
                if str(self.device) == "cuda":
                    self.policy_net.load_state_dict(torch.load(path + model_name))
                else:
                    self.policy_net.load_state_dict(torch.load(path + model_name, map_location=torch.device('cpu')))
            elif re.match(".*_ddqn_.*", model_name):
                self.policy_net = ConvDuelingDQN(self.INPUT_DIM, self.ACTION_NUMBER).to(self.device)
                if str(self.device) == "cuda":
                    self.policy_net.load_state_dict(torch.load(path + model_name))
                else:
                    self.policy_net.load_state_dict(torch.load(path + model_name, map_location=torch.device('cpu')))
            else:
                raise RuntimeError("Please Provide a valid model name or valid path.")
        else:
            raise RuntimeError('Path can not be None if model Name is not None.')

        env_test.reset()  # reset the env st it is set at the beginning of the time serie
        state = env_test.get_state()
        for t in tqdm(range(len(env_test.data))):  # while not env.done

            # Select and perform an action
            action = self.select_action(state)

            reward, done, _ = env_test.step(action)

            cumulative_reward[t] += reward.item() + cumulative_reward[t - 1 if t - 1 > 0 else 0]
            reward_list[t] = reward

            # Observe new state: it will be None if env.done = True. It is the next
            # state since env.step() has been called two rows above.
            next_state = env_test.get_state()

            # Move to the next state
            state = next_state

            if done:
                break

        return cumulative_reward, reward_list