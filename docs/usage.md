## Using the mt5_bridge package in your code

This guide shows how to integrate the file-based MT5 bridge into your Python apps.

### Installation

```bash
pip install -e .
```

### Configure environment

Set the path to your MT5 Data Folder's `MQL5/Files` directory:

```bash
export MT5_FILES_DIR="/path/to/MetaTrader 5/MQL5/Files"
```

Optional environment variables:
- `MT5_PRIMARY_SYMBOL` (default: `XAUUSD`)
- `MT5_PRICE_FILE` (e.g., `XAUUSD!_price.json`) to override auto-detection
- `MT5_TIMEOUT_SEC` heartbeat timeout for price updates (default: 30)
- `MT5_SKIP_HIST_LOG` set to `true/1` to skip historical trade log on first connect

### Quickstart

```python
from mt5_bridge import MT5Connector

connector = MT5Connector()
if not connector.connect():
    raise RuntimeError("Failed to connect to MT5. Check MT5_FILES_DIR and that the EA is running.")

md = connector.get_market_data()
print("Market:", md.symbol, md.bid, md.ask)

# Place a buy
connector.place_buy_order(symbol=md.symbol, lot_size=0.01, comment="example-buy")

# Read positions
positions = connector.get_positions()
print("Open positions:", len(positions))

connector.disconnect()
```

### Context manager

```python
from mt5_bridge import MT5Connector

with MT5Connector() as bridge:
    md = bridge.get_market_data()
    print(md.symbol, md.bid, md.ask)
```

### Singleton helper

```python
from mt5_bridge import get_connector

bridge = get_connector()
bridge.connect()
```

### Trading commands

Place orders:

```python
bridge.place_buy_order(symbol="XAUUSD", lot_size=0.02, stop_loss=2300.0, take_profit=2320.0, comment="strategy-A")
bridge.place_sell_order(symbol="XAUUSD", lot_size=0.02, comment="strategy-B")
```

Modify SL/TP:

```python
bridge.modify_order(ticket=123456789, stop_loss=2310.0, take_profit=2330.0)
```

Close position (full or partial):

```python
bridge.close_position(ticket=123456789)            # full close
bridge.close_position(ticket=123456789, volume=0.1)  # partial close
```

### Reading state and data

Account info:

```python
info = bridge.get_account_info()
print(info.balance, info.equity, info.currency)
```

Open positions:

```python
positions = bridge.get_positions()
for p in positions:
    print(p.ticket, p.symbol, p.type, p.volume, p.profit)
```

Closed trades (recent):

```python
closed = bridge.get_closed_trades(limit=200)
print("Closed trades:", len(closed))
```

Pending orders:

```python
orders = bridge.get_pending_orders()
```

Tick/order book/symbol info and rates:

```python
tick = bridge.get_tick_data()
orderbook = bridge.get_order_book()
symbol_info = bridge.get_symbol_info()
rates_m1 = bridge.get_rates_m1()
```

### Trade results stream

Consume new execution results appended by the EA to `trade_results.txt`:

```python
from time import sleep

while True:
    for result in bridge.get_trade_results():
        print(result.timestamp, result.action, result.result, result.symbol, result.trade_id)
    sleep(1)
```

### Connection health and diagnostics

```python
ok, msg = bridge.test_connection()
print("status:", ok, msg)

stats = bridge.get_connection_info()
print(stats["files_directory"], stats["price_file_exists"])
```

### Error handling and return types

- Most getters return typed dataclasses or dict/list; return `None` or empty list when data is missing.
- Trading methods return `True/False` indicating whether the command was written successfully. Execution success is reported via trade results.

### Tips for development/testing

- You can mock the EA outputs by placing JSON files in `MT5_FILES_DIR` with the expected names (e.g., `XAUUSD_price.json`).
- Ensure the EA is attached to a chart and writing regularly for real-time behavior.

### CLI reference (optional)

```bash
mt5-bridge --files-dir "/path/to/MetaTrader 5/MQL5/Files" --symbol XAUUSD --log-level INFO
```


