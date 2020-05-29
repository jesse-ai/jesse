import numpy as np
from typing import Union

def iqifm(candles: np.ndarray, sequential=False) -> Union[float, np.ndarray]:

    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    Price = (candles[:, 3] + candles[:, 4]) / 2

    Value1  = np.full_like(Price, np.nan)
    InPhase = np.copy(Value1)
    Quadrature  = np.copy(Value1)
    DeltaPhase  = np.copy(Value1)
    InstPeriod  = np.copy(Value1)
    Period  = np.copy(Value1)
    Re = np.copy(Value1)
    Im  = np.copy(Value1)
    Qmult = 0.338
    Imult  = 0.635

    for i in range(8, len(candles)):
        Value1[i] = Price[i] - Price[i-7]
        InPhase[i]  = 1.25 * (Value1[i-4] - Imult * Value1[i-2]) + Imult * InPhase[i-3]
        Quadrature[i]  = Value1[i-2]- Qmult * Value1[i] + Qmult * Quadrature[i-2]
        Re[i]  = .2 * (InPhase[i] * InPhase[i-1] + Quadrature[i] * Quadrature[i-1]) + .8 * Re[i-1]
        Im[i]  = .2 * (InPhase[i] * Quadrature[i-1] - InPhase[i-1] * Quadrature[i]) + .8 * Im[i-1]
        if Re[i] != 0:
            DeltaPhase[i]  = np.arctan(Im[i]/Re[i])

        InstPeriod[i] = 0
        Value4 = 0
        for j in range(50):
            Value4 = Value4 + DeltaPhase[j]
            if Value4 > 360 and InstPeriod[i] == 0:
                InstPeriod[i] = j
        if InstPeriod[i] == 0:
            InstPeriod[i] = InstPeriod[i-1]
            Period[i] = 0.25*InstPeriod[i]  + 0.75*Period[i-1]

    if sequential:
        return Period
    else:
        return None if np.isnan(Period[-1]) else Period[-1]

