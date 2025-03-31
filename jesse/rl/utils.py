#  It essentially maps (state, action) pairs to their (next_state, reward) result,
#  with the state being the current stock price
from collections import namedtuple
import random
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

Transition = namedtuple('Transition', ('state', 'action', 'next_state', 'reward') )


class ReplayMemory(object):

    def __init__(self, capacity):
        self.capacity = capacity
        self.memory = []
        self.position = 0

    def push(self, *args):
        """Saves a transition."""
        if len(self.memory) < self.capacity:
            self.memory.append(None)
        self.memory[self.position] = Transition(*args)
        self.position = (self.position + 1) % self.capacity

    def sample(self, batch_size):
        return random.sample(self.memory, batch_size)

    def __len__(self):
        return len(self.memory)



def print_stats(model, c_return, t):
    c_return = np.array(c_return).flatten()
    t.add_row([str(model), "%.2f" % np.mean(c_return), "%.2f" % np.amax(c_return), "%.2f" % np.amin(c_return),
               "%.2f" % np.std(c_return)])


def plot_conf_interval(name, cum_returns ):
    """ NB. cum_returns must be 2-dim """
    # Mean
    M = np.mean(np.array(cum_returns), axis=0)
    # std dev
    S = np.std(np.array(cum_returns), axis=0)
    # upper and lower limit of confidence intervals
    LL = M - 0.95 * S
    UL = M + 0.95 * S

    plt.figure(figsize=(20, 5))
    plt.xlabel("Trading Instant (h)")
    plt.ylabel(name)
    plt.legend(['Cumulative Averadge Return (%)'], loc='upper left')
    plt.grid(True)
    plt.ylim(-5, 15)
    plt.plot(range(len(M)), M, linewidth=2)  # mean curve.
    plt.fill_between(range(len(M)), LL, UL, color='b', alpha=.2)  # std curves.
    plt.show()

def plot_multiple_conf_interval(names, cum_returns_list ):
    """ NB. cum_returns[i] must be 2-dim """
    i = 1

    for cr in cum_returns_list:
        plt.subplot(len(cum_returns_list), 2, i)
        # Mean
        M = np.mean(np.array(cr), axis=0)
        # std dev
        S = np.std(np.array(cr), axis=0)
        # upper and lower limit of confidence intervals
        LL = M - 0.95 * S
        UL = M + 0.95 * S

        plt.xlabel("Trading Instant (h)")
        plt.ylabel(names[i-1])
        plt.title('Cumulative Averadge Return (%)')
        plt.grid(True)
        plt.plot(range(len(M)), M, linewidth=2)  # mean curve.
        plt.fill_between(range(len(M)), LL, UL, color='b', alpha=.2)  # std curves.
        i += 1

    plt.show()




def load_data(path):
    print("Loading data...")
    print("Path: " + path)
    if os.path.isfile(path + 'hourly_aggregated_dataset.csv'):
        df = pd.read_csv(path + 'hourly_aggregated_dataset.csv')
    else:
        # Aggregate the dataset hourly by picking the value at first row for Open,
        # the max within an hour for High, the minimum for Low, the last value for Close

        df = pd.read_csv(path + 'coinbaseUSD_1-min_data_2014-12-01_to_2019-01-09.csv')
        df_hourly_aggregated = pd.DataFrame()

        for count in range(0, len(df) - 60, 60):
            hour_interval = pd.DataFrame(df.iloc[count:count + 60])
            df_hourly_aggregated = df_hourly_aggregated.append(pd.DataFrame([[hour_interval['Open'].iloc[0],
                                                                              hour_interval['High'].max(),
                                                                              hour_interval['Low'].min(),
                                                                              hour_interval['Close'].iloc[
                                                                                  len(hour_interval) - 1]]]))

        df_hourly_aggregated.columns = ['Open', 'High', 'Low', 'Close']
        df_hourly_aggregated.index = np.arange(1, len(df_hourly_aggregated) + 1)
        df_hourly_aggregated.interpolate(inplace=True)
        df_hourly_aggregated.fillna(method='bfill', axis=0, inplace=True)
        df_hourly_aggregated.to_csv(path + 'hourly_aggregated_dataset.csv', index=False)
        df = df_hourly_aggregated
        del df_hourly_aggregated
    return df