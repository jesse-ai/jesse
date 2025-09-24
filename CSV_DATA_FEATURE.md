# CSV Data Feature for Jesse Trading Framework

This feature adds support for loading custom data from CSV files for backtesting and hyperparameter optimization in Jesse.

## Overview

The CSV data feature allows you to:
- Load tick data from CSV files
- Aggregate tick data into OHLCV candles
- Use custom data sources for backtesting
- Import CSV data into Jesse database
- Access CSV data through REST API endpoints

## Features

### 1. CSV Data Provider (`jesse/services/csv_data_provider.py`)
- Loads tick data from CSV files
- Aggregates tick data into various timeframes (1m, 5m, 1h, etc.)
- Supports data caching for performance
- Handles large CSV files efficiently

### 2. CSV Parser (`jesse/services/csv_parser.py`)
- Parses various CSV formats
- Auto-detects column names
- Converts timestamps to Jesse format
- Supports different timestamp formats

### 3. API Endpoints (`jesse/controllers/csv_controller.py`)
- `/csv/symbols` - Get available symbols
- `/csv/symbols/{symbol}/info` - Get symbol information
- `/csv/symbols/{symbol}/timeframes` - Get available timeframes
- `/csv/import` - Import symbol to database
- `/csv/candles` - Get candles from CSV data
- `/csv/preview/{symbol}` - Preview CSV data
- `/csv/clear-cache` - Clear data cache

## Supported CSV Format

The feature supports CSV files with the following format:
```csv
t,p,v
1672444800000,0.005288,0.0
1672444800001,0.005288,0.0
1672444800002,0.005288,0.0
```

Where:
- `t` - timestamp in milliseconds
- `p` - price
- `v` - volume

## Usage

### 1. Prepare Your Data

Place your CSV files in the following structure:
```
/Users/alxy/Downloads/Fond/KucoinData/
├── SYMBOL1/
│   └── price.csv
├── SYMBOL2/
│   └── price.csv
└── ...
```

### 2. Start Jesse Server

```bash
jesse run
```

### 3. Access CSV Endpoints

The CSV endpoints are available at `http://localhost:9000/csv/`

### 4. Import Data for Backtesting

#### Using API:

```bash
# Get available symbols
curl -X GET "http://localhost:9000/csv/symbols" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Import a symbol to database
curl -X POST "http://localhost:9000/csv/import" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "ACH",
    "timeframe": "1m",
    "exchange": "custom"
  }'

# Get candles
curl -X GET "http://localhost:9000/csv/candles?symbol=ACH&timeframe=1m" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

#### Using Python:

```python
from jesse.services.csv_data_provider import csv_data_provider

# Get available symbols
symbols = csv_data_provider.get_available_symbols()
print(f"Available symbols: {symbols}")

# Get candles for a symbol
candles = csv_data_provider.get_candles(
    symbol="ACH",
    timeframe="1m",
    start_date=1672444800000,  # Optional
    finish_date=1672531200000  # Optional
)

# Import to database
success = csv_data_provider.save_candles_to_database(
    symbol="ACH",
    timeframe="1m",
    exchange="custom"
)
```

### 5. Use in Backtesting

Once data is imported, you can use it in backtesting by setting the exchange to "custom":

```python
# In your backtest configuration
routes = [
    {
        "exchange": "custom",
        "symbol": "ACH",
        "timeframe": "1m",
        "strategy": "YourStrategy"
    }
]
```

## Configuration

### Data Directory

By default, the CSV data provider looks for data in `/Users/alxy/Downloads/Fond/KucoinData/`. You can change this by modifying the `data_directory` parameter in `csv_data_provider.py`:

```python
csv_data_provider = CSVDataProvider(data_directory="/path/to/your/data")
```

### Supported Timeframes

The feature supports all standard Jesse timeframes:
- 1m, 3m, 5m, 15m, 30m, 45m
- 1h, 2h, 3h, 4h, 6h, 8h, 12h
- 1d, 3d, 1w, 1M

## Performance Considerations

- Large CSV files are processed efficiently using pandas
- Data is cached in memory for repeated access
- Use `clear_cache()` to free memory when needed
- Consider using smaller date ranges for very large datasets

## Error Handling

The feature includes comprehensive error handling:
- File not found errors
- Invalid CSV format errors
- Memory errors for very large files
- Database connection errors

## Testing

Run the test script to verify functionality:

```bash
python test_csv_simple.py
```

This will test:
- Data directory structure
- CSV file reading
- Data aggregation
- Basic functionality

## API Reference

### GET /csv/symbols
Get list of available symbols.

**Response:**
```json
{
  "symbols": ["ACH", "BTC", "ETH", ...]
}
```

### GET /csv/symbols/{symbol}/info
Get information about a specific symbol.

**Response:**
```json
{
  "info": {
    "symbol": "ACH",
    "start_time": 1672444800000,
    "end_time": 1758585540003,
    "start_date": "2023-01-01",
    "end_date": "2025-09-22",
    "file_path": "/path/to/file.csv",
    "file_size": 178916630
  }
}
```

### POST /csv/import
Import a symbol to Jesse database.

**Request:**
```json
{
  "symbol": "ACH",
  "timeframe": "1m",
  "exchange": "custom",
  "start_date": "2023-01-01",
  "finish_date": "2023-12-31"
}
```

**Response:**
```json
{
  "message": "Successfully imported ACH to database",
  "symbol": "ACH",
  "timeframe": "1m",
  "exchange": "custom"
}
```

### GET /csv/candles
Get candles from CSV data.

**Parameters:**
- `symbol` - Symbol name
- `timeframe` - Timeframe (default: 1m)
- `exchange` - Exchange name (default: custom)
- `start_date` - Start date (optional)
- `finish_date` - Finish date (optional)

**Response:**
```json
{
  "candles": [
    {
      "time": 1672444800,
      "open": 0.005288,
      "close": 0.005288,
      "high": 0.005288,
      "low": 0.005288,
      "volume": 0.0
    }
  ],
  "count": 1426275,
  "symbol": "ACH",
  "timeframe": "1m",
  "exchange": "custom"
}
```

## Troubleshooting

### Common Issues

1. **File not found**: Make sure CSV files are in the correct directory structure
2. **Memory errors**: Use smaller date ranges or clear cache
3. **Invalid format**: Ensure CSV files have the correct format (t,p,v)
4. **Database errors**: Check database connection and permissions

### Debug Mode

Enable debug logging to see detailed information:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Contributing

When contributing to this feature:
1. Follow the existing code style
2. Add tests for new functionality
3. Update documentation
4. Test with various CSV formats

## License

This feature is part of the Jesse trading framework and follows the same license terms.
