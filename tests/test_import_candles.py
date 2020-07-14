import jesse.helpers as jh
import jesse.modes.import_candles_mode as importer
from tests.data import test_candles_0

test_object_candles = []
for c in test_candles_0:
    test_object_candles.append({
        'id': jh.generate_unique_id(),
        'symbol': 'BTCUSD',
        'exchange': 'Sandbox',
        'timestamp': c[0],
        'open': c[1],
        'high': c[2],
        'low': c[3],
        'close': c[4],
        'volume': c[5]
    })

smaller_data_set = test_object_candles[0:7].copy()


def test_fill_absent_candles():
    assert len(test_object_candles) == 1382

    start = 1553817600000
    end = 1553817600000 + (1440 - 1) * 60000

    fixed_candles = importer._fill_absent_candles(test_object_candles, start, end)

    assert len(fixed_candles) == 1440
    assert fixed_candles[0]['timestamp'] == start
    assert fixed_candles[-1]['timestamp'] == end


def test_fill_absent_candles_beginning_middle_end():
    # Should fill if candles in the beginning are absent
    candles = smaller_data_set[2:7]
    assert len(smaller_data_set) == 7
    assert len(candles) == 5
    start = smaller_data_set[0]['timestamp']
    end = smaller_data_set[-1]['timestamp']
    candles = importer._fill_absent_candles(candles, start, end)
    assert len(candles) == 7
    assert candles[0]['timestamp'] == smaller_data_set[0]['timestamp']
    assert candles[-1]['timestamp'] == smaller_data_set[-1]['timestamp']

    # Should fill if candles in the middle are absent
    candles = smaller_data_set[0:3] + smaller_data_set[5:7]
    assert len(candles) == 5
    candles = importer._fill_absent_candles(candles, start, end)
    assert len(candles) == 7
    assert candles[0]['timestamp'] == smaller_data_set[0]['timestamp']
    assert candles[-1]['timestamp'] == smaller_data_set[-1]['timestamp']

    # Should fill if candles in the ending are absent
    candles = smaller_data_set[0:5]
    assert len(candles) == 5
    candles = importer._fill_absent_candles(candles, start, end)
    assert len(candles) == 7
    assert candles[0]['timestamp'] == smaller_data_set[0]['timestamp']
    assert candles[-1]['timestamp'] == smaller_data_set[-1]['timestamp']


def test_more_than_one_set_of_candles_in_the_middle_are_absent():
    candles = [
                  smaller_data_set[0],
              ] + smaller_data_set[2:3] + smaller_data_set[5:7]
    assert len(smaller_data_set) == 7
    assert len(candles) == 4

    start = smaller_data_set[0]['timestamp']
    end = smaller_data_set[-1]['timestamp']

    candles = importer._fill_absent_candles(candles, start, end)

    assert len(candles) == 7
    assert candles[0]['timestamp'] == start
    assert candles[-1]['timestamp'] == end
