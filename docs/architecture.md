# Architecture

- **EA (MQL5)** writes/reads JSON in the MT5 DataFolder `MQL5/Files/`.
- **Python app** (`src/python/mt5_connector.py`) watches the same folder, parsing:
  - `{SYMBOL}_price.json`, `{SYMBOL}_tick.json`, `{SYMBOL}_orderbook.json`
  - `account_info.json`, `positions.json`, `closed_trades.json`, `orders.json`, `rates_M1.json`, `symbol_info.json`
- Commands are sent as a single flat object in `commands.json` (no array):
  - buy/sell: `{"action":"buy|sell","symbol":"...","lot_size":0.01,"stop_loss":...,"take_profit":...,"comment":"...","magic_number":12345,"trade_id":"..."}`
  - modify: `{"action":"modify","ticket":123456,"stop_loss":...,"take_profit":...}`
  - close: `{"action":"close","ticket":123456,"close_volume":0.01}`
- EA executes commands and appends results to `trade_results.txt`.

This decoupled, file-based IPC is portable and requires no sockets or native bridges.
