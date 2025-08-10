from typing import Union

import numpy as np
from jesse_rust import chande as rust_chande
from jesse.helpers import slice_candles


def chande(candles: np.ndarray, period: int = 22, mult: float = 3.0, direction: str = "long",
           sequential: bool = False) -> Union[float, np.ndarray]:
    """
    Chandelier Exits

    :param candles: np.ndarray
    :param period: int - default: 22
    :param mult: float - default: 3.0
    :param direction: str - default: "long"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)
    
    if direction not in ['long', 'short']:
        raise ValueError('The direction parameter must be \'short\' or \'long\'')
    
    result = rust_chande(candles, period, mult, direction)
    
    return result if sequential else result[-1]
