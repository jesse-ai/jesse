Position Sizing Reference

Fractional sizing example:
```python 
    qty = utils.size_to_qty(
    self.available_margin * fraction,
    self.price,
    fee_rate=self.fee_rate
)
```
Risk-based sizing example:
```python
    qty = utils.risk_to_qty(
    available_margin,
    risk_percent,
    entry_price,
    stop_price,
    fee_rate=self.fee_rate
)
```

Sizing is typically derived from:

- available margin
- entry price
- stop distance
- fee rate

Risk Management Reference Patterns

Exit handling is often implemented using:

- stop_loss
- take_profit
- update_position logic

ATR-based example:

```python
atr = ta.atr(self.candles)

stop_price = entry_price - atr * 2
target_price = entry_price + atr * 3
```
Percentage-based example:
Long position:
```python
stop_price = entry * 0.99
target_price = entry * 1.02
```
Short position uses inverted percentages.

Exit checks can be placed inside update_position().