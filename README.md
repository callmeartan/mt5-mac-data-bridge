## MT5 Mac File Bridge

Professional, open-source bridge for running MetaTrader 5 (MT5) with Python on macOS — without the `MetaTrader5` Python package. The bridge uses a robust, local JSON file IPC so you can stream quotes, monitor positions, and submit trading commands reliably on macOS.

> Built from real trading needs. Optimized for `XAUUSD`, compatible with any symbol.

### Why this bridge

- **macOS-native**: no Windows-only bindings, no Wine, no Docker
- **Stable and simple**: local file IPC (JSON), no sockets to maintain
- **Full flow**: prices, positions, orders, closed trades, and command execution
- **Production-friendly**: structured logs, explicit contracts, minimal dependencies

## Architecture

- The **EA** `mt5/MT5_File_Bridge_Enhanced.mq5` runs inside MT5 and periodically writes:
  - `{SYMBOL}_price.json` (quotes), `{SYMBOL}_tick.json` (tick snapshot), `{SYMBOL}_orderbook.json` (depth, if available)
  - `account_info.json`, `positions.json`, `closed_trades.json`, `orders.json`, `rates_M1.json`, `symbol_info.json`
- The **Python bridge** `src/python/mt5_connector.py` reads those files and writes a flat `commands.json` for actions: `buy`, `sell`, `modify`, `close`. The EA executes and logs results to `trade_results.txt`.

## Features

- **No MetaTrader5 module required** (macOS compatible)
- **Live market data** export at configurable intervals
- **Command interface** for `buy/sell/modify/close` with optional ATR SL/TP (on the EA)
- **Comprehensive state export**: account, positions, pending orders, trade history, symbol specs
- **Detailed execution logs** for auditing and debugging

## Capabilities

- **File-based connection on macOS**: Interacts with the EA via JSON files, no native `MetaTrader5` dependency.
- **Reads live market data**:
  - `{SYMBOL}_price.json` (bid, ask, spread, volume, timestamps)
  - `{SYMBOL}_tick.json` (enriched tick snapshot)
  - `{SYMBOL}_orderbook.json` (depth of market, if available)
  - `rates_M1.json` (compact OHLCV history)
  - `symbol_info.json` (contract specifications)
- **Reads account and trading state**:
  - `account_info.json` (balance, equity, margin, currency, etc.)
  - `positions.json` (open positions)
  - `orders.json` (pending orders)
  - `closed_trades.json` (closed trades from the last 30 days)
- **Sends trading commands** (flat `commands.json`):
  - `buy` / `sell` with `lot_size`, optional `stop_loss`, `take_profit`, `comment`, `magic_number`, `trade_id`
  - `modify` SL/TP by `ticket`
  - `close` full or partial by `ticket` (with `close_volume`)
- **Parses trade results**: Streams new lines from `trade_results.txt` and extracts action, result, symbol, `trade_id`, and tickets for modify/close.
- **Monitors connection health**: Heartbeat via price file timestamps; exposes `get_connection_info()`.
- **Broker compatibility helpers**: Auto-resolves price files across symbol variants (e.g., `XAUUSD` vs `XAUUSD!`) and prefers the freshest file.
- **Usability utilities**: Short in-memory price history, context manager (`with MT5Connector(): ...`), `test_connection()`, `clear_command_file()`.

## Requirements

- macOS with desktop MetaTrader 5 installed
- Python 3.8+

## Installation

### 1) Install the Expert Advisor

- Open MetaTrader 5 → File → Open Data Folder
- Copy `mt5/MT5_File_Bridge_Enhanced.mq5` into `MQL5/Experts/`
- Open MetaEditor (`F4`), compile (`F7`) → expect “0 errors, 0 warnings”
- In MT5: Tools → Options → Expert Advisors → enable "Allow automated trading" and "Allow DLL imports"

### 2) Attach the EA to a chart

- Open a chart (e.g., `XAUUSD`) and set timeframe (M1/M5)
- Drag it from navigation in metatrader 5 `MT5_File_Bridge_Enhanced` onto the chart
- In EA settings, enable "Allow live trading" and "Allow DLL imports"

### 3) Verify in MT5

- Smiley face on the chart, AutoTrading button is green
- Check the Experts tab for startup logs

## Configuration

- **MT5_FILES_DIR**: absolute path to your MT5 DataFolder `MQL5/Files` directory (from MT5: File → Open Data Folder)
- **MT5_PRIMARY_SYMBOL**: preferred symbol (default: `XAUUSD`)
- **MT5_PRICE_FILE**: override price file name (e.g., `XAUUSD!_price.json`)
- **MT5_TIMEOUT_SEC**: heartbeat timeout for file updates (default: `30`)

## Run the bridge

```bash
export MT5_FILES_DIR="/path/to/MetaTrader 5/MQL5/Files"
python3 src/python/mt5_connector.py
```

You should see a connection status and the latest price snapshot. To place a trade, the bridge writes `commands.json` and the EA executes it.

## JSON contracts (concise)

### Price feed — `XAUUSD_price.json`
```json
{
  "symbol": "XAUUSD",
  "bid": 2310.12,
  "ask": 2310.42,
  "volume": 123,
  "timestamp": 1723200000,
  "server_time": "2025.08.09 12:34:56"
}
```

### Command — `commands.json` (flat object)
```json
{
  "action": "buy",
  "symbol": "XAUUSD",
  "lot_size": 0.01,
  "stop_loss": 2305.00,
  "take_profit": 2320.00,
  "comment": "strategy-A#42",
  "magic_number": 12345,
  "trade_id": "uuid-or-timestamp"
}
```

The EA appends results to `trade_results.txt` with: timestamp, action, result, details, symbol, trade_id.

## Repository layout

```
mt5-mac-file-bridge/
├─ mt5/
│  └─ MT5_File_Bridge_Enhanced.mq5
├─ src/
│  └─ python/
│     ├─ mt5_connector.py
│     └─ config_manager.py
├─ examples/
│  ├─ commands.example.json
│  └─ path.hint.txt
├─ docs/
│  └─ architecture.md
├─ LICENSE
├─ CODE_OF_CONDUCT.md
├─ CONTRIBUTING.md
├─ SECURITY.md
└─ README.md
```

## Security and privacy

- **Do not commit credentials** (logins, API keys). Review your `MQL5/Files` artifacts before publishing.
- Prefer demo accounts for testing.

## License

MIT — see `LICENSE`.

## Contributing

Issues and PRs welcome. Please read `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md`.

---

**Author:** Artan Ahmadi — making MT5 ↔ Python workflows smooth on macOS.
