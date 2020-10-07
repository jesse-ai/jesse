# Jesse
[![PyPI](https://img.shields.io/pypi/v/jesse)](https://pypi.org/project/jesse)
[![Downloads](https://pepy.tech/badge/jesse)](https://pepy.tech/project/jesse)
[![Docker Pulls](https://img.shields.io/docker/pulls/salehmir/jesse)](https://hub.docker.com/r/salehmir/jesse)
[![GitHub](https://img.shields.io/github/license/jesse-ai/jesse)](https://github.com/jesse-ai/jesse)

---

[![Website](https://img.shields.io/badge/Website-Start%20here!-9cf)](https://jesse.trade)
[![Docs](https://img.shields.io/badge/Docs-Learn%20how!-red)](https://docs.jesse.trade)
[![Forum](https://img.shields.io/badge/Forum-Join%20us!-brightgreen)](https://forum.jesse.trade)
[![Blog](https://img.shields.io/badge/Blog-Get%20the%20news!-blueviolet)](https://jesse.trade/blog)
---
Jesse is an advanced crypto trading framework which aims to simplify researching and defining trading strategies.

## Why Jesse?
In short, Jesse is more accurate than other solutions, and way more simple. 
In fact, it is so simple that in case you already know Python, you can get started today, in matter of minutes, instead of weeks and months. 

[Here](https://docs.jesse.trade/docs/) you can read more about why Jesse's features. 

## Getting Started
Head over to the "getting started" section of the [documentation](https://docs.jesse.trade/docs/getting-started). The 
documentation is short yet very informative. 

## Example Backtest Results

Check out Jesse's [blog](https://jesse.trade/blog) for tutorials that go through example strategies step by step. 

Here's an example output for a backtest simulation just to get you excited:
```
 CANDLES              |
----------------------+--------------------------
 period               |    974 days (2.67 years)
 starting-ending date | 2018-01-01 => 2020-09-01


 exchange   | symbol   | timeframe   | strategy         |   DNA
------------+----------+-------------+------------------+-------
 Bitfinex   | BTCUSD   | 6h          | TrendFollowing05 |


Executing simulation...  [####################################]  100%
Executed backtest simulation in:  68.13 seconds


 METRICS                         |
---------------------------------+--------------------------------------
 Total Closed Trades             |                                  112
 Total Net Profit                |                   47767.14 (477.67%)
 Starting => Finishing Balance   |                    10000 => 57685.82
 Total Open Trades               |                                    0
 Open PL                         |                                    0
 Total Paid Fees                 |                              10384.3
 Max Drawdown                    |                              -36.05%
 Annual Return                   |                               57.29%
 Expectancy                      |                       426.49 (4.26%)
 Avg Win | Avg Loss              |                     1609.68 | 527.69
 Ratio Avg Win / Avg Loss        |                                 3.05
 Percent Profitable              |                                  45%
 Longs | Shorts                  |                            48% | 52%
 Avg Holding Time                |   3.0 days, 12.0 hours, 16.0 minutes
 Winning Trades Avg Holding Time | 6.0 days, 41.0 minutes, 44.0 seconds
 Losing Trades Avg Holding Time  |    1.0 day, 11.0 hours, 32.0 minutes
 Sharpe Ratio                    |                                 0.99
 Calmar Ratio                    |                                 1.59
 Sortino Ratio                   |                                 2.24
 Omega Ratio                     |                                 1.45
 Winning Streak                  |                                    4
 Losing Streak                   |                                    7
 Largest Winning Trade           |                              9755.96
 Largest Losing Trade            |                              -1859.7
 Total Winning Trades            |                                   50
 Total Losing Trades             |                                   62
```

And here are generated charts:
![chart-example](https://raw.githubusercontent.com/jesse-ai/jesse/master/assets/chart-example.png)

## What's next?
This is the very initial release. There's way more. Subscribe to our mailing list at [jesse.trade](https://jesse.trade) to get the good stuff as soon they're released. Don't worry, We won't send you spam. Pinky promise.

## Community
We've created a [community](http://forum.jesse.trade/) for Jesse users to discuss algo-trading. It's a warm place to share ideas, and help each other out.

## How to contribute
Thank you for your interest in contributing to the project. Before starting to work on a PR, please make sure that it isn't under the "in progress" column in our [Github project page](https://github.com/jesse-ai/jesse/projects/2). In case you want to help but don't know what tasks we need help for, checkout the "todo" column. 

First, you need to install Jesse from the repository instead of PyPi:

```sh
# first, make sure that the PyPi version is not installed
pip uninstall jesse

# now install Jesse from the repository
git clone https://github.com/jesse-ai/jesse.git
cd jesse
pip install -e .
```

Now every change you make to the code will be affected immediately.

After every change, make sure your changes did not break any functionality by running tests:
```
pytest
```

## Disclaimer
This software is for educational purposes only. USE THE SOFTWARE AT YOUR OWN RISK. THE AUTHORS AND ALL AFFILIATES ASSUME NO RESPONSIBILITY FOR YOUR TRADING RESULTS. Do not risk money which you are afraid to lose. There might be bugs in the code - this software DOES NOT come with ANY warranty.
