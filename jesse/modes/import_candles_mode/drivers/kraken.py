import requests

import jesse.helpers as jh
from jesse import exceptions
from .interface import CandleExchange
import pandas as pd
import time


class Kraken(CandleExchange):
    """
    Kraken endpoint for candle data works with timestamps in seconds
    while jesse works with milliseconds
    """

    def __init__(self):
        # kraken sends as many trades as we wish, although, 
        # to be on the safe side we will process only 1000 at a time
        super().__init__('Kraken', 1000, 6)
        self.endpoint = 'https://api.kraken.com/0/public/Trades'

    def init_backup_exchange(self):
        self.backup_exchange = None

    def get_starting_time(self, symbol):
        payload = {
            'pair': symbol,
            'since': 000,
        }

        response = requests.get(self.endpoint, params=payload)
        self._handle_errors(response)

        data = response.json()
        candlesDF = self._tradeconversion(data, symbol, limit=self.count)
        return candlesDF["timestamp"][0].value

    def fetch(self, symbol, start_timestamp):
        df = self._fetchDF(symbol, start_timestamp)
        return df.to_dict(orient="records")

    def _fetchDF(self, symbol, start_timestamp):
        payload = {
            'pair': symbol,
            'since': start_timestamp * 10**6,
        }

        response = requests.get(self.endpoint, params=payload)
        self._handle_errors(response)
        data = response.json()["result"][self._topair(symbol)]
        candlesDF = self._tradeconversion(data, symbol, limit=self.count)
        while len(candlesDF.index) < self.count:
            time.sleep(self.sleep_time)
            nextTstamp = (candlesDF.index[-1] - pd.Timestamp("1970-01-01")) // pd.Timedelta("1ns")
            payload["since"] = nextTstamp
            response = requests.get(self.endpoint, params=payload)
            self._handle_errors(response)
            data = response.json()["result"][self._topair(symbol)]
            nextCandlesDF = self._tradeconversion(data, symbol, limit=self.count)
            nextCandlesDF.drop(candlesDF.index, inplace=True, errors="ignore")
            candlesDF = candlesDF.append(nextCandlesDF, sort=True)
        return candlesDF

    def _topair(self, symbol):
        return "X{}Z{}".format(symbol[:3], symbol[3:]).upper()

    def _tradeconversion(self, data, symbol, limit=-1):
        # if no limit given, we discard the last candle anyway
        trades = []
        volumes = []
        tstamps = []
        for trade in data:
            trades.append(float(trade[0]))
            volumes.append(float(trade[1]))
            tstamps.append(pd.to_datetime(trade[2], unit="s"))
        tradeSeries = pd.Series(data=trades, index=tstamps)
        volumeSeries = pd.Series(data=volumes, index=tstamps)
        grouper = pd.Grouper(freq="1Min", base=0)
        vols = volumeSeries.groupby(grouper).sum()
        trds = tradeSeries.groupby(grouper).ohlc()
        candls = trds
        candls.loc[:, "volume"] = vols
        # always throw away the last candle
        candls = candls[0:-1]
        candls = candls[0:limit]
        candls = candls.fillna(method="ffill")
        candls.loc[:, "id"] = [jh.generate_unique_id() for idx in range(len(candls.index))]
        candls.loc[:, "symbol"] = symbol
        candls.loc[:, "exchange"] = self.name
        candls.loc[:, "timestamp"] = (candls.index - pd.Timestamp("1970-01-01")) // pd.Timedelta("1ms")
        return candls

    @staticmethod
    def _handle_errors(response):
        # Exchange In Maintenance
        if response.status_code == 502:
            raise exceptions.ExchangeInMaintenance('ERROR: 502 Bad Gateway. Please try again later')
        # unsupported symbol
        if response.status_code == 404:
            raise ValueError(response.json()['message'])
        # generic error
        if response.status_code != 200:
            raise Exception(response.content)
        # error in body
        if response.json()["error"]:
            raise Exception(response.json()["error"])
