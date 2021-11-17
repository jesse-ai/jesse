# Jesse beta (GUI dashboard)

Here's a quick guide on how to set up and run the dashboard branch until it is officially released.

First, you need to set up Jesse from the source code if you haven't already:
```sh
# first, make sure that the PyPi version is not installed
pip uninstall jesse

# now install Jesse from the repository
git clone https://github.com/jesse-ai/jesse.git
cd jesse
pip install -e .
```

Then you need to switch to the `beta` branch:
```sh
git checkout beta
```

Now go to your Jesse project (where you used to run backtest command, etc) and first create a `.env` file with the below configuration:

```sh
nano .env
```

```
PASSWORD=test

POSTGRES_HOST=127.0.0.1
POSTGRES_NAME=jesse_db
POSTGRES_PORT=5432
POSTGRES_USERNAME=jesse_user
POSTGRES_PASSWORD=password

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 
# Live Trade Only                                                                 # 
# =============================================================================== #
# Below values don't concern you if you haven't installed the live trade plugin   #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 

# For all notifications
GENERAL_TELEGRAM_BOT_TOKEN=
GENERAL_TELEGRAM_BOT_CHAT_ID=
GENERAL_DISCORD_WEBHOOK=

# For error notifications only
ERROR_TELEGRAM_BOT_TOKEN=
ERROR_TELEGRAM_BOT_CHAT_ID=
ERROR_DISCORD_WEBHOOK=

# Testnet Binance Futures: 
# http://testnet.binancefuture.com
TESTNET_BINANCE_FUTURES_API_KEY=
TESTNET_BINANCE_FUTURES_API_SECRET=

# Binance Futures: 
# https://www.binance.com/en/futures/btcusdt
BINANCE_FUTURES_API_KEY=
BINANCE_FUTURES_API_SECRET=

# FTX Futures: 
# https://ftx.com/markets/future
FTX_FUTURES_API_KEY=
FTX_FUTURES_API_SECRET=
# leave empty if it's the main account and not a subaccount
FTX_FUTURES_SUBACCOUNT_NAME=
```

Of course, you should change the values to your config if you're not using the default values. Also, don't forget to change the `PASSWORD` as you need it for logging in. You no longer need `routes.py` and `config.py`, or even `live-config.py` files in your Jesse project. You can delete them if you want.

## New Requirements
First, install Redis which is a requirement for this application. I will add guides for different environments but for now, you should be able to find guides on the net. On a mac, it's as easy as running `brew install redis`. On Ubuntu 20.04:

```sh
sudo apt update -y
sudo apt install redis-server -y
# The supervised directive is set to no by default. So let's edit it:
sudo nano /etc/redis/redis.conf
# Find the line that says `supervised no` and change it to `supervised systemd`
sudo systemctl restart redis.service
```

Then you need to install few pip packages as well. A quick way to install them all is by running:
```sh
pip install -r https://raw.githubusercontent.com/jesse-ai/jesse/beta/requirements.txt
```

## Database migration
It is important to migrate the database before running the application. I created a simple Jesse command that will do it for you:
```sh
jesse migrate
```

## Start the application

To get the party started, (inside your Jesse project) run the application by:
```
jesse run
```

And it will print a local URL for you to open in your browser such as:
```
INFO:     Started server process [66103]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

So go ahead and open (in my case) `http://127.0.0.1:8000` in your browser of choice. If you are running on a server, you can use the IP address of the server instead of 
`127.0.0.1`. So for example if the IP address of your server is `1.2.3.4` the URL would be `http://1.2.3.4:8000`. I will soon add instructions on how to secure the remote server that is running the application.

## Live Trade Plugin
To install the beta version of the live trade plugin, first, make sure to uninstall the previous one:
```
pip uninstall jesse-live
```

Now you need to change your account on Jesse.Trade as a beta user. You'll find it at your [profile](https://jesse.trade/user/profile) page:

![user profile beta](https://raw.githubusercontent.com/jesse-ai/storage/master/singles/user-profile-beta.jpg)

Now you can see the latest beta version on the [releases](http://jesse.trade/releases) page. Download and install it as always. 

## Disclaimer
**This is version is the beta version of an early-access plugin! That means you should NOT use it in production yet! If done otherwise, you and only your are responsible.**