#!/usr/bin/env python3
"""
Test script for the fill missing candles functionality in backtest scenario
"""
import numpy as np
import sys
import os

# Add the jesse directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jesse'))

from jesse.services.candle import _get_generated_candles
import jesse.helpers as jh

def test_backtest_scenario():
    """Test the fill missing candles functionality in a backtest scenario"""
    
    print("Testing backtest scenario with insufficient data...")
    
    # Simulate 1-minute candles for 10 minutes (should be enough for 5m candles, but not for 15m)
    trading_candles = np.array([
        [1640995200000, 100.0, 101.0, 102.0, 99.0, 1000],   # 1m candle 1
        [1640995260000, 101.0, 102.0, 103.0, 100.0, 1100],  # 1m candle 2
        [1640995320000, 102.0, 103.0, 104.0, 101.0, 1200],  # 1m candle 3
        [1640995380000, 103.0, 104.0, 105.0, 102.0, 1300],  # 1m candle 4
        [1640995440000, 104.0, 105.0, 106.0, 103.0, 1400],  # 1m candle 5
        [1640995500000, 105.0, 106.0, 107.0, 104.0, 1500],  # 1m candle 6
        [1640995560000, 106.0, 107.0, 108.0, 105.0, 1600],  # 1m candle 7
        [1640995620000, 107.0, 108.0, 109.0, 106.0, 1700],  # 1m candle 8
        [1640995680000, 108.0, 109.0, 110.0, 107.0, 1800],  # 1m candle 9
        [1640995740000, 109.0, 110.0, 111.0, 108.0, 1900],  # 1m candle 10
    ])
    
    print(f"Input: {len(trading_candles)} 1-minute candles")
    
    # Test 5m timeframe (should work fine)
    print("\nTesting 5m timeframe generation...")
    try:
        candles_5m = _get_generated_candles('5m', trading_candles)
        print(f"✅ Generated {len(candles_5m)} 5m candles")
        for i, candle in enumerate(candles_5m):
            print(f"   5m candle {i+1}: {candle}")
    except Exception as e:
        print(f"❌ Error generating 5m candles: {e}")
        return False
    
    # Test 15m timeframe (should fill missing data)
    print("\nTesting 15m timeframe generation...")
    try:
        candles_15m = _get_generated_candles('15m', trading_candles)
        print(f"✅ Generated {len(candles_15m)} 15m candles")
        for i, candle in enumerate(candles_15m):
            print(f"   15m candle {i+1}: {candle}")
    except Exception as e:
        print(f"❌ Error generating 15m candles: {e}")
        return False
    
    # Test 1h timeframe (should fill missing data)
    print("\nTesting 1h timeframe generation...")
    try:
        candles_1h = _get_generated_candles('1h', trading_candles)
        print(f"✅ Generated {len(candles_1h)} 1h candles")
        for i, candle in enumerate(candles_1h):
            print(f"   1h candle {i+1}: {candle}")
    except Exception as e:
        print(f"❌ Error generating 1h candles: {e}")
        return False
    
    return True

def test_without_fill_missing_in_backtest():
    """Test backtest behavior when fill_missing_candles is disabled"""
    
    print("\n" + "="*60)
    print("Testing backtest without fill missing candles (should fail)...")
    
    # Mock the config to disable fill_missing_candles
    import jesse.config as config_module
    import jesse.helpers as jh_helpers
    
    # Clear the config cache
    if hasattr(jh_helpers, 'CACHED_CONFIG'):
        jh_helpers.CACHED_CONFIG.clear()
    
    original_config = config_module.config.copy()
    config_module.config['env']['data']['fill_missing_candles'] = False
    
    # Simulate insufficient data
    trading_candles = np.array([
        [1640995200000, 100.0, 101.0, 102.0, 99.0, 1000],
        [1640995260000, 101.0, 102.0, 103.0, 100.0, 1100],
    ])
    
    try:
        candles_15m = _get_generated_candles('15m', trading_candles)
        print(f"❌ Unexpected success: generated {len(candles_15m)} 15m candles")
        return False
    except ValueError as e:
        if "Insufficient data" in str(e):
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
    print("Testing Fill Missing Candles in Backtest Scenario")
    print("=" * 60)
    
    success1 = test_backtest_scenario()
    success2 = test_without_fill_missing_in_backtest()
    
    print("\n" + "=" * 60)
    if success1 and success2:
        print("✅ All backtest tests passed!")
    else:
        print("❌ Some backtest tests failed!")
    print("=" * 60)
