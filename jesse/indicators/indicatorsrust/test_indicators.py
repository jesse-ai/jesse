import numpy as np
from jesse.indicators.indicatorsrust import rsi, kama, ichimoku_cloud, smma, shift, alligator, srsi, moving_std, sma
from jesse.indicators import bollinger_bands, mean_ad, median_ad

# Test RSI
print("Testing RSI...")
source = np.array([10.0, 11.0, 10.5, 11.5, 12.0, 11.8, 12.5, 12.2, 11.5, 11.8, 12.0, 12.5, 13.0, 12.8], dtype=np.float64)
result = rsi(source, 5)
print(f"RSI result shape: {result.shape}")
print(f"Last value: {result[-1]}")

# Test KAMA
print("\nTesting KAMA...")
result = kama(source, 5, 2, 30)
print(f"KAMA result shape: {result.shape}")
print(f"Last value: {result[-1]}")

# Test Ichimoku Cloud
print("\nTesting Ichimoku Cloud...")
# Create a simple candle array with OHLC data
# Format: timestamp, open, close, high, low, volume
candles = np.array([
    [1, 10.0, 11.0, 12.0, 9.5, 100],
    [2, 11.0, 10.5, 11.5, 10.0, 150],
    [3, 10.5, 11.5, 12.0, 10.2, 200],
    [4, 11.5, 12.0, 12.5, 11.0, 300],
    [5, 12.0, 11.8, 12.2, 11.5, 250],
    [6, 11.8, 12.5, 12.8, 11.7, 320],
    [7, 12.5, 12.2, 12.7, 12.0, 200],
    [8, 12.2, 11.5, 12.3, 11.2, 150],
    [9, 11.5, 11.8, 12.0, 11.3, 180],
    [10, 11.8, 12.0, 12.1, 11.7, 220],
    [11, 12.0, 12.5, 12.7, 11.9, 250],
    [12, 12.5, 13.0, 13.2, 12.4, 300],
    [13, 13.0, 12.8, 13.3, 12.6, 270],
    [14, 12.8, 12.9, 13.1, 12.7, 220],
    [15, 12.9, 13.1, 13.3, 12.8, 240],
    [16, 13.1, 13.2, 13.4, 13.0, 260],
    [17, 13.2, 13.0, 13.3, 12.9, 200],
    [18, 13.0, 13.3, 13.5, 12.9, 230],
    [19, 13.3, 13.4, 13.6, 13.2, 250],
    [20, 13.4, 13.5, 13.7, 13.3, 280],
    # Add more candles to meet the minimum requirement for Ichimoku
    [21, 13.5, 13.6, 13.8, 13.4, 290],
    [22, 13.6, 13.7, 13.9, 13.5, 300],
    [23, 13.7, 13.8, 14.0, 13.6, 310],
    [24, 13.8, 13.9, 14.1, 13.7, 320],
    [25, 13.9, 14.0, 14.2, 13.8, 330],
    # Add more candles...
], dtype=np.float64)

# We need more data for Ichimoku
# Create more synthetic data
for i in range(26, 100):
    new_candle = np.array([[i, 14.0 + i*0.1, 14.1 + i*0.1, 14.3 + i*0.1, 13.9 + i*0.1, 300 + i]], dtype=np.float64)
    candles = np.vstack([candles, new_candle])

conversion_line, base_line, span_a, span_b = ichimoku_cloud(candles, 9, 26, 52, 26)
print(f"Conversion Line: {conversion_line}")
print(f"Base Line: {base_line}")
print(f"Span A: {span_a}")
print(f"Span B: {span_b}")

# Test SMMA
print("\nTesting SMMA...")
result = smma(source, 5)
print(f"SMMA result shape: {result.shape}")
print(f"Last few values: {result[-5:]}")

# Test Shift
print("\nTesting Shift...")
shifted = shift(source, 2)  # Shift right by 2
print(f"Shifted result shape: {shifted.shape}")
print(f"Original: {source}")
print(f"Shifted (by 2): {shifted}")

# Test Alligator
print("\nTesting Alligator...")
jaw, teeth, lips = alligator(source)
print(f"Jaw shape: {jaw.shape}, Teeth shape: {teeth.shape}, Lips shape: {lips.shape}")
print(f"Jaw last value: {jaw[-1]}")
print(f"Teeth last value: {teeth[-1]}")
print(f"Lips last value: {lips[-1]}")

# Test SRSI
print("\nTesting SRSI...")
# Create price data with alternating up and down movements
price_data = []
price = 100.0
for i in range(100):
    if i % 5 == 0:
        price += 2.0
    elif i % 3 == 0:
        price -= 1.5
    else:
        price += 0.2
    price_data.append(price)

# Convert to numpy array
price_array = np.array(price_data, dtype=np.float64)

# Calculate RSI first for reference
rsi_values = rsi(price_array, 14)
print("First few RSI values:")
for i in range(14, 20):
    print(f"RSI[{i}] = {rsi_values[i]}")

# Calculate SRSI
k, d = srsi(price_array, 14, 14, 3, 3)
print(f"SRSI shape: K={k.shape}, D={d.shape}")
print("First few valid SRSI values:")
start_idx = 14 + 14 + 3 + 3  # Approximate point where we should have valid values
for i in range(start_idx, start_idx + 5):
    if i < len(k):
        print(f"K[{i}] = {k[i]}, D[{i}] = {d[i]}")

print("Last few SRSI values:")
for i in range(len(k) - 5, len(k)):
    print(f"K[{i}] = {k[i]}, D[{i}] = {d[i]}")

# Test Bollinger Bands
print("\nTesting Bollinger Bands...")
upper, middle, lower = bollinger_bands(price_array, period=20, devup=2, devdn=2, sequential=True)
print(f"Bollinger Bands shapes: U={upper.shape}, M={middle.shape}, L={lower.shape}")
first_valid_idx = 0
for i in range(len(middle)):
    if not np.isnan(middle[i]):
        first_valid_idx = i
        break
print("First few valid Bollinger Bands values:")
for i in range(first_valid_idx, first_valid_idx + 5):
    if i < len(middle):
        print(f"Index {i}: U={upper[i]:.2f}, M={middle[i]:.2f}, L={lower[i]:.2f}")

print("Last few Bollinger Bands values:")
for i in range(len(middle) - 5, len(middle)):
    print(f"Index {i}: U={upper[i]:.2f}, M={middle[i]:.2f}, L={lower[i]:.2f}")

# Test SMA
print("\nTesting SMA...")
sma_values = sma(price_array, period=15)
print(f"SMA shape: {sma_values.shape}")
first_valid_idx = 0
for i in range(len(sma_values)):
    if not np.isnan(sma_values[i]):
        first_valid_idx = i
        break
print("First few valid SMA values:")
for i in range(first_valid_idx, first_valid_idx + 5):
    if i < len(sma_values):
        print(f"SMA[{i}] = {sma_values[i]:.2f}")

print("Last few SMA values:")
for i in range(len(sma_values) - 5, len(sma_values)):
    print(f"SMA[{i}] = {sma_values[i]:.2f}")

print("\nAll tests completed successfully!") 