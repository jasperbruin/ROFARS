import statistics
import time
import numpy as np
import pandas as pd
from tqdm import tqdm
from rofarsEnv import ROFARS_v1
from agents import baselineAgent, LSTM_Agent, DiscountedUCBAgent, SlidingWindowUCBAgent, UCBAgent
import torch
from torch import nn
from torch.optim import Adam
import csv
import matplotlib.pyplot as plt
from random import shuffle
from sklearn.utils import resample


if not torch.backends.mps.is_available():
    if not torch.backends.mps.is_built():
        print("MPS not available because the current PyTorch install was not "
              "built with MPS enabled.")
    else:
        print("MPS not available because the current MacOS version is not 12.3+"
              "and/or you do not have an MPS-enabled device on this machine.")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

else:
    device = torch.device("mps")


def create_training_traces(env, mode, inp):
    # Training
    env.reset(mode)
    if inp == 1:
        baseline_agent = baselineAgent(agent_type='strong')
        states = []

        # Generate training traces from the Baseline agent
        init_action = np.random.rand(env.n_camera)
        reward, state, stop = env.step(init_action)

        for t in tqdm(range(env.length), initial=2):
            action = baseline_agent.get_action(state)
            reward, state, stop = env.step(action)

            states.append(state)

            if stop:
                break

        return states

    elif inp == 2:
        states = []
        agent = DiscountedUCBAgent(gamma=0.999)
        agent.initialize(env.n_camera)

        for t in tqdm(range(env.length), initial=2):
            action = agent.get_action()
            reward, state, stop = env.step(action)

            # Update the UCB Agent
            agent.update(action, state)

            states.append(state)

            if stop:
                break

        return states
    elif inp == 3:
        states = []
        agent = SlidingWindowUCBAgent(window_size=9*60)
        agent.initialize(env.n_camera)

        for t in tqdm(range(env.length), initial=2):
            action = agent.get_action()
            reward, state, stop = env.step(action)

            # Update the UCB Agent
            agent.update(action, state)

            states.append(state)

            if stop:
                break

        return states
    elif inp == 4:
        states = []
        agent = UCBAgent()
        agent.initialize(env.n_camera)

        for t in tqdm(range(env.length), initial=2):
            action = agent.get_action()
            reward, state, stop = env.step(action)

            # Update the UCB Agent
            agent.update(action, state)

            states.append(state)

            if stop:
                break

        return states
    elif inp == 5:
        baseline_agent = baselineAgent(agent_type='simple')
        states = []

        # Generate training traces from the Baseline agent
        init_action = np.random.rand(env.n_camera)
        reward, state, stop = env.step(init_action)

        for t in tqdm(range(env.length), initial=2):
            action = baseline_agent.get_action(state)
            reward, state, stop = env.step(action)

            states.append(state)

            if stop:
                break

        return states


baseline_agent = None
agent = None

def get_train_test(states, split_percent=0.7):
    n = len(states)
    split = int(n * split_percent)
    train_states = states[:split]
    test_states = states[split:]
    return train_states, test_states

def get_XY(states, time_steps=1):
    states = np.array(states)
    X, Y = [], []
    for i in range(len(states) - time_steps):
        X.append(states[i : (i + time_steps)])
        Y.append(states[i + time_steps])
    return np.array(X), np.array(Y)

def impute_missing_values(states):
    # median impuation
    imputed_states = []
    for state in states:
        median_values = np.median([v for v in state if v >= 0])
        imputed_state = np.array([v if v >= 0 else median_values for v in state])
        imputed_states.append(imputed_state)
    return np.array(imputed_states)

def imv(state):
    median_value = np.median([v for v in state if v >= 0])
    imputed_state = np.array([v if v >= 0 else median_value for v in state])
    return imputed_state


def resample_data(X, Y):
    X_resampled, Y_resampled = resample(X, Y, replace=True, n_samples=len(X) // 2, random_state=123)
    c = list(zip(X_resampled, Y_resampled))
    shuffle(c)
    X_resampled, Y_resampled = zip(*c)

    return X_resampled, Y_resampled

def robustness_test(agent_type, budget_ratios):
    rewards = []
    l_rate = 0.001
    hidden_size = 16
    time_steps = 60
    epochs = 2500
    patience = 10
    epochs_without_improvement = 0
    best_val_loss = float('inf')
    training_losses = []
    validation_losses = []

    for budget_ratio in budget_ratios:
        env = ROFARS_v1(budget_ratio=budget_ratio)
        env.reset(mode='test')

        # inp2 = int(input("1. Baseline Agent 2. D-UCB Agent: 3. SW-UCB Agent 4. UCB-1 Agent\n"))
        if agent_type == 1:
            agent = baselineAgent(agent_type='strong')
        elif agent_type == 2:
            agent = DiscountedUCBAgent(gamma=0.999)
            agent.initialize(env.n_camera)
        elif agent_type == 3:
            agent = SlidingWindowUCBAgent(window_size=9*60)
            agent.initialize(env.n_camera)
        elif agent_type == 4:
            agent = UCBAgent()
            agent.initialize(env.n_camera)
        elif agent_type == 5:
            agent = baselineAgent(agent_type='simple')




        # Retraining the agent
        train_data = create_training_traces(env, 'train', agent_type)
        test_data = create_training_traces(env, 'test', agent_type)

        train_data = impute_missing_values(train_data)
        test_data = impute_missing_values(test_data)

        lstm_agent = LSTM_Agent(input_size, hidden_size, output_size).to(device)
        optimizer = Adam(lstm_agent.parameters(), lr=l_rate)

        # # Use the function on your data
        trainX, trainY = get_XY(train_data, time_steps)
        testX, testY = get_XY(test_data, time_steps)

        trainX, trainY = resample_data(trainX, trainY)

        trainX = np.array(trainX)

        trainX = torch.tensor(trainX, dtype=torch.float32).to(device)
        trainY = torch.tensor(trainY, dtype=torch.float32).to(device)
        testX = torch.tensor(testX, dtype=torch.float32).to(device)
        testY = torch.tensor(testY, dtype=torch.float32).to(device)

        # Training loop
        print('Training LSTM Agent')
        for epoch in range(epochs):
            hidden_state, cell_state = lstm_agent.init_hidden_cell_states(
                batch_size=trainX.size(0))
            hidden_state = hidden_state.to(device)
            cell_state = cell_state.to(device)
            optimizer.zero_grad()
            outputs, (hidden_state, cell_state) = lstm_agent(trainX, (
                hidden_state, cell_state))
            loss = criterion(outputs, trainY)
            loss.backward()

            optimizer.step()

            # Validation
            val_outputs, (_, _) = lstm_agent(testX,
                                             lstm_agent.init_hidden_cell_states(
                                                 batch_size=testX.size(0)))
            hidden_state = hidden_state.to(device)
            cell_state = cell_state.to(device)
            val_loss = criterion(val_outputs, testY)
            validation_losses.append(round(val_loss.item(),
                                           3))  # Append the reward at each timestep
            training_losses.append(
                round(loss.item(), 3))  # Append the reward at each timestep

            # Early stopping
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                epochs_without_improvement = 0
                best_epoch = epoch
            else:
                epochs_without_improvement += 1

            print(
                f'Epoch: {epoch + 1}, Training Loss: {round(loss.item(), 3)}, Validation Loss: {round(val_loss.item(), 3)}')

            if epochs_without_improvement >= patience:
                print("Early stopping")
                break

        print(f'Testing LSTM Agent on budget ratio {budget_ratio}')
        env.reset(mode='test')
        # give random scores as the initial action
        init_action = np.random.rand(env.n_camera)
        reward, state, stop = env.step(init_action)

        # Initialize the hidden and cell states for the LSTM agent
        hidden_state, cell_state = lstm_agent.init_hidden_cell_states(
            batch_size=1)
        hidden_state = hidden_state.to(device)
        cell_state = cell_state.to(device)

        inference_times = []

        reward_on_time = []
        for t in tqdm(range(env.length), initial=2):
            # Prepare the input state for the LSTM agent
            # print(state)
            input_state = torch.tensor(state, dtype=torch.float32).unsqueeze(
                0).unsqueeze(0).to(
                device)  # Add the batch and sequence dimensions


            # Get the action from the LSTM agent, passing the hidden and cell states
            action, (hidden_state, cell_state) = lstm_agent(input_state, (
                hidden_state, cell_state))

            action = action.squeeze().detach().cpu().numpy()

            # Perform the action in the environment
            reward, state, stop = env.step(action)
            reward_on_time.append(reward)

            state = impute_missing_values([state])[0]

            if stop:
                break


        rewards.append(env.get_total_reward())
        print('[total reward]:', env.get_total_reward())
        print('[Hyperparameters]')
        print(
            "epochs: {} lr: {} \nhidden_size: {} time_steps: {} loss function: {}".format(
                epochs, l_rate, hidden_size, time_steps, inp1))

    return budget_ratios, rewards



if __name__ == '__main__':
    inp1 = int(input("1. MSE\n2. MAE \n3. Huber\n4. LogCosh\n"))
    if inp1 == 1:
        criterion = nn.MSELoss()
    if inp1 == 2:
        criterion = nn.L1Loss()
    if inp1 == 3:
        criterion = nn.HuberLoss()


    np.random.seed(0)

    env = ROFARS_v1()

    input_size = env.n_camera
    output_size = env.n_camera
    #inp2 = int(input("1. Baseline Agent 2. D-UCB Agent: 3. SW-UCB Agent 4. UCB-1 Agent\n"))


    budget_ratios = [0.1, 0.3, 0.5, 0.7, 0.9]

    # Pass budget_ratios as an argument to the robustness_test() function
    budget_ratios, rewards_strong_baseline = robustness_test(1, budget_ratios)
    budget_ratios, rewards_d_ucb = robustness_test(2, budget_ratios)
    budget_ratios, rewards_sw_ucb = robustness_test(3, budget_ratios)
    budget_ratios, rewards_ucb1 = robustness_test(4, budget_ratios)
    budget_ratios, rewards_simple_baseline = robustness_test(5, budget_ratios)

    print('Length of budget_ratios:', len(budget_ratios))
    print('Length of rewards_ucb1:', len(rewards_ucb1))
    print('Length of rewards_sw_ucb:', len(rewards_sw_ucb))
    print('Length of rewards_d_ucb:', len(rewards_d_ucb))
    print('Length of rewards_simple_baseline:', len(rewards_simple_baseline))
    print('Length of rewards_strong_baseline:', len(rewards_strong_baseline))

    # # save results to csv
    df = pd.DataFrame({'budget_ratios': budget_ratios,
                       'rewards_ucb1': rewards_ucb1,
                       'rewards_sw_ucb': rewards_sw_ucb,
                       'rewards_d_ucb': rewards_d_ucb,
                       'rewards_simple_baseline': rewards_simple_baseline,
                       'rewards_strong_baseline': rewards_strong_baseline})
    df.to_csv('robustness_test2.csv', index=False)
