import math
import numpy as np
from tqdm import tqdm
from rofarsEnv import ROFARS_v1
from agents import baselineAgent, LSTM_Agent, DiscountedUCBAgent
from sklearn.metrics import mean_squared_error
import matplotlib.pyplot as plt
import torch
from torch import nn
from torch.optim import Adam
from bayes_opt import BayesianOptimization

batch_size = 32

inp = int(input("1. MSE\n2. MAE \n3. Huber\n"))
if inp == 1:
    criterion = nn.MSELoss()
if inp == 2:
    criterion = nn.L1Loss()
if inp == 3:
    criterion = nn.SmoothL1Loss()

def get_train_test(states, split_percent=0.8):
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
    imputed_states = []
    for state in states:
        mean_values = np.mean([v for v in state if v >= 0])
        imputed_state = np.array([v if v >= 0 else mean_values for v in state])
        imputed_states.append(imputed_state)
    return np.array(imputed_states)


def create_training_traces(env, mode, inp):

    # Training
    env.reset(mode)
    if inp == 1:
        baseline_agent = baselineAgent()
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


def train_and_evaluate(params):
    hidden_size, time_steps, epochs = map(int, params)

    lstm_agent = LSTM_Agent(input_size, hidden_size, output_size)
    optimizer = Adam(lstm_agent.parameters(), lr=0.001)
    criterion = nn.L1Loss()

    trainX, trainY = get_XY(train_data, time_steps)
    testX, testY = get_XY(test_data, time_steps)

    trainX = torch.tensor(trainX, dtype=torch.float32)
    trainY = torch.tensor(trainY, dtype=torch.float32)
    testX = torch.tensor(testX, dtype=torch.float32)
    testY = torch.tensor(testY, dtype=torch.float32)

    # Training loop
    for epoch in range(epochs):
        for i in range(0, len(trainX), batch_size):
            x_batch = trainX[i : i + batch_size]
            y_batch = trainY[i : i + batch_size]

            optimizer.zero_grad()
            outputs = lstm_agent(x_batch)
            loss = criterion(outputs, y_batch)
            loss.backward()
            optimizer.step()

    # Make predictions
    train_predict = lstm_agent(trainX).detach().numpy()
    test_predict = lstm_agent(testX).detach().numpy()

    # Print error
    train_rmse = math.sqrt(mean_squared_error(trainY.numpy(), train_predict))
    test_rmse = math.sqrt(mean_squared_error(testY.numpy(), test_predict))

    return train_rmse, test_rmse


def optimize_lstm_agent(epochs, hidden_size, time_steps):
    _, test_rmse = train_and_evaluate((hidden_size, time_steps, epochs))
    return -test_rmse




# Plot the result
def plot_result(trainY, testY, train_predict, test_predict):
    actual = np.append(trainY, testY)
    predictions = np.append(train_predict, test_predict)
    rows = len(actual)
    plt.figure(figsize=(15, 6), dpi=80)
    plt.plot(range(rows), actual)
    plt.plot(range(rows), predictions)
    plt.axvline(x=len(trainY), color='r')
    plt.legend(['Actual', 'Predictions'])
    plt.xlabel('Observation number after given time steps')
    plt.ylabel('Sunspots scaled')
    plt.title('Actual and Predicted Values. The Red Line Separates The Training And Test Examples')
    plt.show()

def print_error(trainY, testY, train_predict, test_predict):
    # Error of predictions
    train_rmse = math.sqrt(mean_squared_error(trainY, train_predict))
    test_rmse = math.sqrt(mean_squared_error(testY, test_predict))
    # Print RMSE
    print('Train RMSE: %.3f RMSE' % (train_rmse))
    print('Test RMSE: %.3f RMSE' % (test_rmse))


if __name__ == '__main__':
    np.random.seed(0)

    env = ROFARS_v1()

    input_size = env.n_camera
    output_size = env.n_camera
    inp = int(input("1. Baseline Agent 2. UCB Agent: "))

    train_data = create_training_traces(env, 'train', inp)
    test_data = create_training_traces(env, 'test', inp)

    train_data = impute_missing_values(train_data)
    test_data = impute_missing_values(test_data)

    pbounds = {
        'hidden_size': (16, 64),
        'time_steps': (1, 20),
        'epochs': (10, 40)
    }

    optimizer = BayesianOptimization(
        f=optimize_lstm_agent,
        pbounds=pbounds,
        verbose=2,
        random_state=1,
    )

    optimizer.maximize(init_points=5, n_iter=10)

    best_params = optimizer.max['params']
    hidden_size = int(best_params['hidden_size'])
    time_steps = int(best_params['time_steps'])
    epochs = int(best_params['epochs'])

    print(
        f"Best parameters: Hidden size: {hidden_size}, Time steps: {time_steps}, Epochs: {epochs}")

    lstm_agent = LSTM_Agent(input_size, hidden_size, output_size)
    optimizer = Adam(lstm_agent.parameters(), lr=0.001)

    trainX, trainY = get_XY(train_data, time_steps)
    testX, testY = get_XY(test_data, time_steps)

    trainX = torch.tensor(trainX, dtype=torch.float32)
    trainY = torch.tensor(trainY, dtype=torch.float32)
    testX = torch.tensor(testX, dtype=torch.float32)
    testY = torch.tensor(testY, dtype=torch.float32)



    # Training loop
    for epoch in range(epochs):
        for i in range(0, len(trainX), batch_size):
            x_batch = trainX[i: i + batch_size]
            y_batch = trainY[i: i + batch_size]

            optimizer.zero_grad()
            outputs = lstm_agent(x_batch)
            loss = criterion(outputs, y_batch)
            loss.backward()
            optimizer.step()

        print(f'Epoch: {epoch + 1}, Loss: {round(loss.item(), 3)}')

    # Make predictions
    train_predict = lstm_agent(trainX).detach().numpy()
    test_predict = lstm_agent(testX).detach().numpy()

    # Print error
    print_error(trainY.numpy(), testY.numpy(), train_predict, test_predict)

    # Plot result
    plot_result(trainY.numpy(), testY.numpy(), train_predict, test_predict)


"""
-- activation: None
Baseline Agent results, huber loss:
Best parameters: Hidden size: 28, Time steps: 19, Epochs: 39
Train RMSE: 0.724 RMSE
Test RMSE: 0.703 RMSE

UCB Agent results, huber loss:
Best parameters: Hidden size: 28, Time steps: 20, Epochs: 16
Epoch: 16, Loss: 0.23
Train RMSE: 0.723 RMSE
Test RMSE: 0.704 RMSE


--------
-- activation: relu
Baseline Agent results, huber loss:
"""
