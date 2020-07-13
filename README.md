# Jesse
[![Python Version](https://img.shields.io/badge/python-3.6%20%7C%203.7%20%7C%203.8-blue)](https://www.python.org/)
[![PyPI](https://img.shields.io/pypi/v/jesse)](https://pypi.org/project/jesse)
[![Docker Pulls](https://img.shields.io/docker/pulls/salehmir/jesse)](https://hub.docker.com/r/salehmir/jesse)
[![GitHub](https://img.shields.io/github/license/jesse-ai/jesse)](https://github.com/jesse-ai/jesse)
[![Build Status](https://travis-ci.com/jesse-ai/jesse.svg?branch=master)](https://travis-ci.com/jesse-ai/jesse)
[![codecov](https://codecov.io/gh/jesse-ai/jesse/branch/master/graph/badge.svg)](https://codecov.io/gh/jesse-ai/jesse)

---
[![Website](https://img.shields.io/badge/Website-Start%20here!-9cf)](https://jesse-ai.com)
[![Docs](https://img.shields.io/badge/Docs-Learn%20how!-red)](https://docs.jesse-ai.com)
[![Forum](https://img.shields.io/badge/Forum-Join%20us!-brightgreen)](https://forum.jesse-ai.com)
[![Blog](https://img.shields.io/badge/Blog-Get%20the%20news!-blueviolet)](https://jesse-ai.com/blog)
---
Jesse is an advanced crypto trading framework which aims to simplify researching and defining trading strategies.

## Why Jesse?
In short, Jesse is more accurate than other solutions, and way more simple. 
In fact, it is so simple that in case you already know Python, you can get started today, in matter of minutes, instead of weeks and months.

## Getting Started
Head over to the "getting started" section of the [documentation](https://docs.jesse-ai.com/docs/getting-started). The 
documentation is short yet very informative. 

## Example Backtest Results

Check out Jesse's [blog](https://jesse-ai.com/blog) for tutorials that go through example strategies step by step. 

Here's an example output for a backtest simulation just to get you excited:
```
CANDLES               |
----------------------+--------------------------
 period               |   1557 days (4.27 years)
 starting-ending date | 2016-01-01 => 2020-04-06

exchange    | symbol   | timeframe   | strategy           | DNA
------------+----------+-------------+--------------------+-------
 Bitfinex   | BTCUSD   | 6h          | TrendFollowingStrategy |

Executing simulation...  [####################################]  100%
Executed backtest simulation in:  107.89 seconds

METRICS                          |
---------------------------------+------------------------------------
 Total Closed Trades             |                                192
 Total Net Profit                |                 64735.12 (647.35%)
 Starting => Finishing Balance   |                   10000 => 74659.0
 Total Open Trades               |                                  0
 Open PL                         |                                  0
 Total Paid Fees                 |                           10620.84
 Max Drawdown                    |                            -24.83%
 Sharpe Ratio                    |                                1.2
 Annual Return                   |                             38.43%
 Expectancy                      |                     337.16 (3.37%)
 Avg Win | Avg Loss              |                   1261.49 | 351.89
 Ratio Avg Win / Avg Loss        |                               3.58
 Percent Profitable              |                                43%
 Longs | Shorts                  |                          58% | 42%
 Avg Holding Time                | 3.0 days, 20.0 hours, 15.0 minutes
 Winning Trades Avg Holding Time | 6.0 days, 11.0 hours, 19.0 minutes
 Losing Trades Avg Holding Time  |  1.0 day, 21.0 hours, 14.0 minutes
```

And here are generated charts:
![chart-example](https://raw.githubusercontent.com/jesse-ai/jesse/master/assets/chart-example.png)

## What's next?
This is the very initial release. There's way more. Subscribe to our mailing list at [jesse-ai.com](https://jesse-ai.com) to get the good stuff as soon they're released. Don't worry, We won't send you spam. Pinky promise.

## Community
We've created a [community](http://forum.jesse-ai.com/) for Jesse users to discuss algo-trading. It's a warm place to share ideas, and help each other out.

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
