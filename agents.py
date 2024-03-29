"""
agent script for 'Resource Optimization for Facial Recognition Systems (ROFARS)' project
author: Cyril Hsu & Jasper Bruin @ UvA-MNS
date: 23/02/2023
"""


from collections import deque
import numpy as np
import torch
import torch.nn as nn


def select_device():
    """
    Set the device to MPS if available, else to CUDA if available, else CPU.

    Returns:
        torch.device : The selected device.
    """
    if not torch.backends.mps.is_available():
        if not torch.backends.mps.is_built():
            print(
                "MPS not available because the current PyTorch install was not built with MPS enabled.")
        else:
            print(
                "MPS not available because the current MacOS version is not 12.3+ or there is no MPS-enabled device.")

        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        return torch.device("mps")


device = select_device()


class baselineAgent:
    """
    A baseline agent class that either selects actions randomly or based on previous states.

    Attributes
    ----------
    agent_type : str
        Type of the agent. Must be either 'simple' (for random action selection) or
        'strong' (for action selection based on previous states).
    prev_state : array
        The previous state observed by the agent.
    theta : float
        Parameter for the strong agent to replace -1 values in the previous state.
    """
    def __init__(self, theta=0, agent_type='strong'):
        assert agent_type in ['simple', 'strong']
        self.agent_type = agent_type
        self.prev_state = None
        self.theta = theta

    def initialize(self, n_actions):
        pass

    def get_action(self, state):
        # store previous state
        self.prev_state = state

        if self.agent_type=='simple':
            # random action
            action = np.random.rand(len(state))

        elif self.agent_type=='strong':
            # use previous states as scores (-1 is replaced by the learned param theta)
            action = np.array([v if v>=0 else self.theta for v in self.prev_state])

        return action

class SlidingWindowUCBAgent:
    """
    Agent implementing Sliding Window UCB algorithm for action selection.

    Attributes
    ----------
    window_size : int
        The size of the sliding window for recent rewards and counts.
    """
    def __init__(self, window_size=1000):
        self.counts = None
        self.values = None
        self.c = 3
        self.window_size = window_size
        self.recent_rewards = None
        self.recent_counts = None
        self.recent_rewards_sum = None
        self.recent_counts_sum = None
        self.total_time_steps = 0

    def initialize(self, n_actions):
        self.counts = np.zeros(n_actions)
        self.values = np.zeros(n_actions)
        self.recent_rewards = [deque(maxlen=self.window_size) for _ in range(n_actions)]
        self.recent_counts = [deque(maxlen=self.window_size) for _ in range(n_actions)]
        self.recent_rewards_sum = np.zeros(n_actions)
        self.recent_counts_sum = np.zeros(n_actions)

    def get_action(self):
        if self.counts.min() == 0:
            idx = np.random.choice(np.where(self.counts == 0)[0])
            action = np.zeros(len(self.values))
            action[idx] = 1
        else:
            min_time_steps = min(self.total_time_steps, self.window_size)
            recent_values = self.recent_rewards_sum / self.recent_counts_sum
            ucb_values = recent_values + self.c * np.sqrt(
                2 * np.log(min_time_steps) / self.recent_counts_sum)
            action = ucb_values
        return action

    def update(self, actions, state):
        self.total_time_steps += 1
        for i, reward in enumerate(state):
            if reward >= 0:
                self.counts[i] += 1

                if len(self.recent_rewards[i]) == self.window_size:
                    self.recent_rewards_sum[i] -= self.recent_rewards[i][0]
                    self.recent_counts_sum[i] -= self.recent_counts[i][0]

                self.recent_rewards[i].append(reward)
                self.recent_counts[i].append(1)
                self.recent_rewards_sum[i] += reward
                self.recent_counts_sum[i] += 1
            else:
                self.counts[i] += 0
                self.recent_rewards[i].append(0)
                self.recent_counts[i].append(0)


class DiscountedUCBAgent:
    """
    Agent implementing Discounted UCB algorithm for action selection.

    Attributes
    ----------
    gamma : float
        Discount factor for past rewards and counts.
    """
    def __init__(self, gamma=0.9):
        self.counts = None
        self.discounted_counts = None
        self.values = None
        self.discounted_rewards = None
        self.c = 3
        self.gamma = gamma
        self.total_time_steps = 0

    def initialize(self, n_actions):
        self.counts = np.zeros(n_actions)
        self.discounted_counts = np.zeros(n_actions)
        self.values = np.zeros(n_actions)
        self.discounted_rewards = np.zeros(n_actions)

    def get_action(self):
        if self.counts.min() == 0:
            idx = np.random.choice(np.where(self.counts == 0)[0])
            action = np.zeros(len(self.values))
            action[idx] = 1
        else:
            discounted_means = self.discounted_rewards / self.discounted_counts
            ct_numerator = 2 * np.log(self.total_time_steps)
            ct_denominator = self.discounted_counts
            ct = self.c * np.sqrt(np.maximum(ct_numerator / ct_denominator, 0))
            action = discounted_means + ct
        return action

    def update(self, actions, state):
        self.total_time_steps = self.gamma*self.total_time_steps + 1
        self.discounted_counts *= self.gamma
        self.discounted_rewards *= self.gamma

        for i, reward in enumerate(state):
            if reward >= 0:
                self.counts[i] += 1
                self.values[i] += reward

                self.discounted_counts[i] += 1
                self.discounted_rewards[i] += reward
            else:
                self.counts[i] += 0


class UCBAgent:
    """
    Agent implementing UCB1 algorithm for action selection.

    Attributes
    ----------
    None
    """
    def __init__(self):
        self.counts = None
        self.values = None
        self.c = 3
        self.total_time_steps = 0

    def initialize(self, n_actions):
        self.counts = np.zeros(n_actions)
        self.values = np.zeros(n_actions)

    def get_action(self):
        if self.counts.min() == 0:
        # action = np.random. choice(np.where(self.counts == 0) [0])
            idx = np.random.choice(np.where(self.counts == 0)[0])
            action = np.zeros(len(self.values))
            action[idx] = 1
        else:
            ucb_values = self.values + self.c * np.sqrt(2 * np.log(self.total_time_steps) / self.counts)
            action = ucb_values
        return action

    def update(self, actions, state):
        self.total_time_steps += 1
        for i, reward in enumerate(state):
            if reward >= 0:
                self.counts[i] += 1
                self.values[i] = self.values[i] + (1 / self.counts[i]) * (reward - self.values[i])
            else:
                self.counts[i] += 0

class LSTM_Agent(nn.Module):
    """
    LSTM Agent is a type of agent which makes use of a LSTM network for action selection.

    Attributes
    ----------
    input_size : int
        The number of expected features in the input.
    hidden_size : int
        The number of features in the hidden state of LSTM.
    output_size : int
        The number of expected features in the output.
    """
    def __init__(self, input_size, hidden_size, output_size):
        super(LSTM_Agent, self).__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, batch_first=True)
        self.dense = nn.Linear(hidden_size, output_size)
        self.records = [[] for _ in range(input_size)]
        self.hidden_size = hidden_size

    def forward(self, state, hidden_cell):
        x, hidden_cell = self.lstm(state, hidden_cell)
        x = x[:, -1, :]
        x = self.dense(x)
        return x, hidden_cell

    def init_hidden_cell_states(self, batch_size):
        hidden_state = torch.zeros(1, batch_size, self.hidden_size).to(device)
        cell_state = torch.zeros(1, batch_size, self.hidden_size).to(device)
        return hidden_state, cell_state




