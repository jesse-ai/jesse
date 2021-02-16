from typing import Union

import numpy as np
import talib

from jesse.helpers import get_config


def pattern_recognition(candles: np.ndarray, pattern_type: str, penetration: int = 0, sequential: bool = False) -> \
        Union[int, np.ndarray]:
    """
    Pattern Recognition

    :param candles: np.ndarray
    :param penetration: int - default = 0
    :param pattern_type: str
    :param sequential: bool - default=False

    :return: int | np.ndarray
    """
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    if pattern_type == "CDL2CROWS":
        res = talib.CDL2CROWS(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDL3BLACKCROWS":
        res = talib.CDL3BLACKCROWS(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDL3INSIDE":
        res = talib.CDL3INSIDE(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDL3LINESTRIKE":
        res = talib.CDL3LINESTRIKE(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDL3OUTSIDE":
        res = talib.CDL3OUTSIDE(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDL3STARSINSOUTH":
        res = talib.CDL3STARSINSOUTH(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDL3WHITESOLDIERS":
        res = talib.CDL3WHITESOLDIERS(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLABANDONEDBABY":
        res = talib.CDLABANDONEDBABY(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2],
                                     penetration=penetration)
    elif pattern_type == "CDLADVANCEBLOCK":
        res = talib.CDLADVANCEBLOCK(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLBELTHOLD":
        res = talib.CDLBELTHOLD(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLBREAKAWAY":
        res = talib.CDLBREAKAWAY(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLCLOSINGMARUBOZU":
        res = talib.CDLCLOSINGMARUBOZU(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLCONCEALBABYSWALL":
        res = talib.CDLCONCEALBABYSWALL(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLCOUNTERATTACK":
        res = talib.CDLCOUNTERATTACK(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLDARKCLOUDCOVER":
        res = talib.CDLDARKCLOUDCOVER(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2],
                                      penetration=penetration)
    elif pattern_type == "CDLDOJI":
        res = talib.CDLDOJI(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLDOJISTAR":
        res = talib.CDLDOJISTAR(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLDRAGONFLYDOJI":
        res = talib.CDLDRAGONFLYDOJI(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLENGULFING":
        res = talib.CDLENGULFING(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLEVENINGDOJISTAR":
        res = talib.CDLEVENINGDOJISTAR(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2],
                                       penetration=penetration)
    elif pattern_type == "CDLEVENINGSTAR":
        res = talib.CDLEVENINGSTAR(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2], penetration=penetration)
    elif pattern_type == "CDLGAPSIDESIDEWHITE":
        res = talib.CDLGAPSIDESIDEWHITE(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLGRAVESTONEDOJI":
        res = talib.CDLGRAVESTONEDOJI(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLHAMMER":
        res = talib.CDLHAMMER(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLHANGINGMAN":
        res = talib.CDLHANGINGMAN(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLHARAMI":
        res = talib.CDLHARAMI(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLHARAMICROSS":
        res = talib.CDLHARAMICROSS(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLHIGHWAVE":
        res = talib.CDLHIGHWAVE(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLHIKKAKE":
        res = talib.CDLHIKKAKE(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLHIKKAKEMOD":
        res = talib.CDLHIKKAKEMOD(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLHOMINGPIGEON":
        res = talib.CDLHOMINGPIGEON(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLIDENTICAL3CROWS":
        res = talib.CDLIDENTICAL3CROWS(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLINNECK":
        res = talib.CDLINNECK(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLINVERTEDHAMMER":
        res = talib.CDLINVERTEDHAMMER(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLKICKING":
        res = talib.CDLKICKING(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLKICKINGBYLENGTH":
        res = talib.CDLKICKINGBYLENGTH(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLLADDERBOTTOM":
        res = talib.CDLLADDERBOTTOM(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLLONGLEGGEDDOJI":
        res = talib.CDLLONGLEGGEDDOJI(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLLONGLINE":
        res = talib.CDLLONGLINE(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLMARUBOZU":
        res = talib.CDLMARUBOZU(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLMATCHINGLOW":
        res = talib.CDLMATCHINGLOW(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLMATHOLD":
        res = talib.CDLMATHOLD(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2], penetration=penetration)
    elif pattern_type == "CDLMORNINGDOJISTAR":
        res = talib.CDLMORNINGDOJISTAR(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2],
                                       penetration=penetration)
    elif pattern_type == "CDLMORNINGSTAR":
        res = talib.CDLMORNINGSTAR(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2], penetration=penetration)
    elif pattern_type == "CDLONNECK":
        res = talib.CDLONNECK(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLPIERCING":
        res = talib.CDLPIERCING(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLRICKSHAWMAN":
        res = talib.CDLRICKSHAWMAN(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLRISEFALL3METHODS":
        res = talib.CDLRISEFALL3METHODS(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLSEPARATINGLINES":
        res = talib.CDLSEPARATINGLINES(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLSHOOTINGSTAR":
        res = talib.CDLSHOOTINGSTAR(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLSHORTLINE":
        res = talib.CDLSHORTLINE(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLSPINNINGTOP":
        res = talib.CDLSPINNINGTOP(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLSTALLEDPATTERN":
        res = talib.CDLSTALLEDPATTERN(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLSTICKSANDWICH":
        res = talib.CDLSTICKSANDWICH(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLTAKURI":
        res = talib.CDLTAKURI(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLTASUKIGAP":
        res = talib.CDLTASUKIGAP(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLTHRUSTING":
        res = talib.CDLTHRUSTING(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLTRISTAR":
        res = talib.CDLTRISTAR(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLUNIQUE3RIVER":
        res = talib.CDLUNIQUE3RIVER(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLUPSIDEGAP2CROWS":
        res = talib.CDLUPSIDEGAP2CROWS(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    elif pattern_type == "CDLXSIDEGAP3METHODS":
        res = talib.CDLXSIDEGAP3METHODS(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])
    else:
        raise ValueError('pattern type string not recognised')

    return res / 100 if sequential else res[-1] / 100
