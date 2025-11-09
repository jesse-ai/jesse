#!/usr/bin/env python3
"""
Convert Binance CSV format to Jesse-compatible CSV format

Binance format:
Open time,Open,High,Low,Close,Volume,Close time,Quote asset volume,Number of trades,...

Jesse format:
timestamp,open,close,high,low,volume

Where timestamp is in milliseconds
"""

import pandas as pd
from datetime import datetime
import sys


def convert_binance_to_jesse(input_file: str, output_file: str):
    """
    Convert Binance CSV to Jesse format

    Args:
        input_file: Path to Binance CSV file
        output_file: Path to output Jesse CSV file
    """
    print(f"📂 Reading Binance CSV: {input_file}")

    # Read the Binance CSV
    df = pd.read_csv(input_file)

    # Strip whitespace from column names and string columns
    df.columns = df.columns.str.strip()
    if 'Open time' in df.columns:
        df['Open time'] = df['Open time'].str.strip()

    print(f"✅ Loaded {len(df)} rows")

    # Remove rows with NaN timestamps
    df = df.dropna(subset=['Open time'])
    print(f"📊 Valid rows after cleanup: {len(df)}")
    print(f"📅 Date range: {df['Open time'].iloc[0]} to {df['Open time'].iloc[-1]}")

    # Convert timestamp to milliseconds
    print("🔄 Converting timestamps to milliseconds...")
    # Parse the datetime string properly and convert to milliseconds
    df['timestamp'] = pd.to_datetime(df['Open time']).astype('int64') // 1_000_000

    # Create Jesse format dataframe
    jesse_df = pd.DataFrame({
        'timestamp': df['timestamp'],
        'open': df['Open'],
        'close': df['Close'],
        'high': df['High'],
        'low': df['Low'],
        'volume': df['Volume']
    })

    # Sort by timestamp (should already be sorted, but just in case)
    jesse_df = jesse_df.sort_values('timestamp')

    # Remove duplicates if any
    initial_count = len(jesse_df)
    jesse_df = jesse_df.drop_duplicates(subset=['timestamp'], keep='first')
    removed = initial_count - len(jesse_df)

    if removed > 0:
        print(f"⚠️  Removed {removed} duplicate timestamps")

    # Validate data
    print("\n🔍 Data validation:")
    print(f"   Total candles: {len(jesse_df)}")
    print(f"   Start: {datetime.fromtimestamp(jesse_df['timestamp'].iloc[0] / 1000)}")
    print(f"   End: {datetime.fromtimestamp(jesse_df['timestamp'].iloc[-1] / 1000)}")
    print(f"   Timeframe: 15m")

    # Check for missing values
    missing = jesse_df.isnull().sum()
    if missing.any():
        print(f"⚠️  Warning: Found missing values:")
        print(missing[missing > 0])

    # Save to CSV
    print(f"\n💾 Saving Jesse format CSV: {output_file}")
    jesse_df.to_csv(output_file, index=False)

    print(f"✅ Conversion complete!")
    print(f"\n📋 Summary:")
    print(f"   Input rows: {len(df)}")
    print(f"   Output rows: {len(jesse_df)}")
    print(f"   File size: {round(len(open(output_file).read()) / 1024 / 1024, 2)} MB")

    return jesse_df


if __name__ == "__main__":
    input_file = "btc_15m_data_2018_to_2025.csv"
    output_file = "btc_15m_jesse_format.csv"

    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    if len(sys.argv) > 2:
        output_file = sys.argv[2]

    convert_binance_to_jesse(input_file, output_file)
