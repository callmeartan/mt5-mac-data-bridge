# Contributing

Thanks for helping improve MT5 Mac File Bridge!

## Development setup
1. Clone the repo
2. Create a Python venv and install dev deps:
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements-dev.txt
   ```

## Pull requests
- Keep PRs focused and small when possible.
- Include a clear description and testing notes.
- Do not include credentials or private paths in commits.

## Commit style
Use clear, imperative commit messages:
- `feat: add ATR-based SL/TP toggle`
- `fix: handle missing commands.json gracefully`
