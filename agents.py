# agent script for 'Resource Optimization for Facial Recognition Systems (ROFARS)' project
# author: Cyril Hsu @ UvA-MNS
# date: 23/02/2023
from collections import deque
import numpy as np
import torch
import torch.nn as nn


class baselineAgent:

    def __init__(self, theta=0, agent_type='strong'):
        assert agent_type in ['simple', 'strong']
        self.agent_type = agent_type
        self.prev_state = None
        self.theta = theta

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
    def __init__(self, window_size=100):
        self.counts = None
        self.values = None
        self.c = 3
        self.window_size = window_size
        self.recent_rewards = None
        self.recent_counts = None
        self.total_time_steps = 0

    def initialize(self, n_actions):
        self.counts = np.zeros(n_actions)
        self.values = np.zeros(n_actions)
        self.recent_rewards = [deque(maxlen=self.window_size) for _ in range(n_actions)]
        self.recent_counts = [deque(maxlen=self.window_size) for _ in range(n_actions)]

    def get_action(self):
        if self.counts.min() == 0:
            idx = np.random.choice(np.where(self.counts == 0)[0])
            action = np.zeros(len(self.values))
            action[idx] = 1
        else:
            min_time_steps = min(self.total_time_steps, self.window_size)
            recent_counts_sum = np.array([sum(counts) for counts in self.recent_counts])
            ucb_values = self.values + self.c * np.sqrt(2 * np.log(min_time_steps) / recent_counts_sum)
            action = ucb_values
        return action


    def update(self, actions, state):
        self.total_time_steps += 1
        for i, reward in enumerate(state):
            if reward >= 0:
                self.counts[i] += 1
                self.recent_rewards[i].append(reward)
                self.recent_counts[i].append(1)

                # Calculate the average reward based on the sliding window
                avg_reward = sum(self.recent_rewards[i]) / sum(self.recent_counts[i])
                self.values[i] = avg_reward
            else:
                self.counts[i] += 0
                self.recent_counts[i].append(0)

class DiscountedUCBAgent:
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
    def __init__(self, input_size, hidden_size, output_size):
        super(LSTM_Agent, self).__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, batch_first=True)
        self.dense = nn.Linear(hidden_size, output_size)
        self.records = [[] for _ in range(input_size)]
        self.hidden_size = hidden_size

    def forward(self, state):
        x, _ = self.lstm(state)
        x = x[:, -1, :]
        x = self.dense(x)
        x = torch.relu(x)
        return x

    def initialize(self, n_actions):
        pass

    def get_action(self, state):
        state_tensor = torch.tensor(state, dtype=torch.float32).unsqueeze(0)
        with torch.no_grad():
            output = self.forward(state_tensor)
        action = output.numpy().squeeze()
        return action

    def update(self, actions, state):
        for i, reward in enumerate(state):
            if reward >= 0:
                self.records[i].append(reward)