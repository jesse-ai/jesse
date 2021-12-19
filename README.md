# Jesse
[![PyPI](https://img.shields.io/pypi/v/jesse)](https://pypi.org/project/jesse)
[![Downloads](https://pepy.tech/badge/jesse)](https://pepy.tech/project/jesse)
[![Docker Pulls](https://img.shields.io/docker/pulls/salehmir/jesse)](https://hub.docker.com/r/salehmir/jesse)
[![GitHub](https://img.shields.io/github/license/jesse-ai/jesse)](https://github.com/jesse-ai/jesse)

---

[![Website](https://img.shields.io/badge/Website-Start%20here!-9cf)](https://jesse.trade)
[![Docs](https://img.shields.io/badge/Docs-Learn%20how!-red)](https://docs.jesse.trade)
[![FAQ](https://img.shields.io/badge/FAQ-Find%20answers!-yellow)](https://jesse.trade/help)
[![Chat](https://img.shields.io/discord/771690508413829141)](https://jesse.trade/discord)
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
 period               |   1792 days (4.91 years)
 starting-ending date | 2016-01-01 => 2020-11-27


 exchange   | symbol   | timeframe   | strategy         | DNA
------------+----------+-------------+------------------+-------
 Bitfinex   | BTC-USD   | 6h          | TrendFollowing05 |


Executing simulation...  [####################################]  100%
Executed backtest simulation in:  135.85 seconds


 METRICS                         |
---------------------------------+------------------------------------
 Total Closed Trades             |                                221
 Total Net Profit                |            1,699,245.56 (1699.25%)
 Starting => Finishing Balance   |            100,000 => 1,799,245.56
 Total Open Trades               |                                  0
 Open PL                         |                                  0
 Total Paid Fees                 |                         331,480.93
 Max Drawdown                    |                            -22.42%
 Annual Return                   |                             80.09%
 Expectancy                      |                   7,688.89 (7.69%)
 Avg Win | Avg Loss              |                 31,021.9 | 8,951.7
 Ratio Avg Win / Avg Loss        |                               3.47
 Percent Profitable              |                                42%
 Longs | Shorts                  |                          60% | 40%
 Avg Holding Time                | 3.0 days, 22.0 hours, 50.0 minutes
 Winning Trades Avg Holding Time |  6.0 days, 14.0 hours, 9.0 minutes
 Losing Trades Avg Holding Time  |   2.0 days, 1.0 hour, 41.0 minutes
 Sharpe Ratio                    |                               1.88
 Calmar Ratio                    |                               3.57
 Sortino Ratio                   |                               3.51
 Omega Ratio                     |                               1.49
 Winning Streak                  |                                  5
 Losing Streak                   |                                 10
 Largest Winning Trade           |                         205,575.89
 Largest Losing Trade            |                         -50,827.92
 Total Winning Trades            |                                 92
 Total Losing Trades             |                                129
```

And here are generated charts:
![chart-example](https://raw.githubusercontent.com/jesse-ai/jesse/master/assets/chart-example.png)

## What's next?
This is the very initial release. There's way more. Subscribe to our mailing list at [jesse.trade](https://jesse.trade) to get the good stuff as soon they're released. Don't worry, We won't send you spam. Pinky promise.

## Community
I created a [discord server](https://jesse.trade/discord) for Jesse users to discuss algo-trading. It's a warm place to share ideas, and help each other out.

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
