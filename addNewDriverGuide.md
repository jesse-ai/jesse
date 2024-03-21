## Steps for adding a new driver for BACKTEST (import candles):

1. Add it to enum
2. Add it to info.py
3. Create the driver for import-candles
4. Add it to modes/import_candles_mode/drivers/__init__.py
 
================================================

## Steps for adding a new driver for LIVE:
- Implement the driver class
- Add it to jesse_live/exchanges/__init__.py
- Add it to config['app']['live_drivers'] in live plugin's config.py
- Add .env values for the driver
- Update EXCLUDE_FILES in jesse-live's setup.py

## Steps for adding a new driver in Laravel project:
- add driver name without dashes in the validateLicense method in ApiController file
