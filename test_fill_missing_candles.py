#!/usr/bin/env python3
"""
Test script for the fill missing candles functionality
"""
import numpy as np
import sys
import os

# Add the jesse directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jesse'))

from jesse.services.candle import generate_candle_from_one_minutes
import jesse.helpers as jh

def test_fill_missing_candles():
    """Test the fill missing candles functionality"""
    
    # Test data - only 8 candles instead of 15 required for 15m timeframe
    test_candles = np.array([
        [1640995200000, 100.0, 101.0, 102.0, 99.0, 1000],  # 1m candle 1
        [1640995260000, 101.0, 102.0, 103.0, 100.0, 1100], # 1m candle 2
        [1640995320000, 102.0, 103.0, 104.0, 101.0, 1200], # 1m candle 3
        [1640995380000, 103.0, 104.0, 105.0, 102.0, 1300], # 1m candle 4
        [1640995440000, 104.0, 105.0, 106.0, 103.0, 1400], # 1m candle 5
        [1640995500000, 105.0, 106.0, 107.0, 104.0, 1500], # 1m candle 6
        [1640995560000, 106.0, 107.0, 108.0, 105.0, 1600], # 1m candle 7
        [1640995620000, 107.0, 108.0, 109.0, 106.0, 1700], # 1m candle 8
    ])
    
    print("Testing fill missing candles functionality...")
    print(f"Input candles: {len(test_candles)} candles")
    print(f"Required for 15m timeframe: {jh.timeframe_to_one_minutes('15m')} candles")
    
    try:
        # This should work now with fill_missing_candles=True (default)
        result = generate_candle_from_one_minutes('15m', test_candles, accept_forming_candles=False)
        print(f"✅ Success! Generated 15m candle: {result}")
        print(f"   Timestamp: {result[0]}")
        print(f"   Open: {result[1]}")
        print(f"   Close: {result[2]}")
        print(f"   High: {result[3]}")
        print(f"   Low: {result[4]}")
        print(f"   Volume: {result[5]}")
        
        # Verify the result makes sense
        assert result[1] == test_candles[0][1], "Open price should match first candle's open"
        assert result[2] == test_candles[-1][2], "Close price should match last candle's close"
        assert result[3] >= max(test_candles[:, 3]), "High should be at least the max high"
        assert result[4] <= min(test_candles[:, 4]), "Low should be at most the min low"
        assert result[5] == sum(test_candles[:, 5]), "Volume should be sum of all volumes"
        
        print("✅ All assertions passed!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    return True

def test_without_fill_missing():
    """Test behavior when fill_missing_candles is disabled"""
    
    # Mock the config to disable fill_missing_candles
    import jesse.config as config_module
    import jesse.helpers as jh_helpers
    
    # Clear the config cache
    if hasattr(jh_helpers, 'CACHED_CONFIG'):
        jh_helpers.CACHED_CONFIG.clear()
    
    original_config = config_module.config.copy()
    config_module.config['env']['data']['fill_missing_candles'] = False
    
    test_candles = np.array([
        [1640995200000, 100.0, 101.0, 102.0, 99.0, 1000],
        [1640995260000, 101.0, 102.0, 103.0, 100.0, 1100],
    ])
    
    print("\nTesting without fill missing candles (should fail)...")
    print(f"Input candles: {len(test_candles)} candles")
    print(f"Required for 15m timeframe: {jh.timeframe_to_one_minutes('15m')} candles")
    
    try:
        result = generate_candle_from_one_minutes('15m', test_candles, accept_forming_candles=False)
        print(f"❌ Unexpected success: {result}")
        return False
    except ValueError as e:
        if "Sent only" in str(e) and "required to create" in str(e):
            print(f"✅ Expected error: {e}")
            return True
        else:
            print(f"❌ Unexpected error type: {e}")
            return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    finally:
        # Restore original config
        config_module.config = original_config

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Fill Missing Candles Functionality")
    print("=" * 60)
    
    success1 = test_fill_missing_candles()
    success2 = test_without_fill_missing()
    
    print("\n" + "=" * 60)
    if success1 and success2:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed!")
    print("=" * 60)