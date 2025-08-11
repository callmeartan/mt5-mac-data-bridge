#!/usr/bin/env python3
"""Compatibility shim.

This script now lives in the package `mt5_bridge`. Prefer:

    pip install -e .
    mt5-bridge --log-level INFO

or:

    from mt5_bridge import MT5Connector

"""

import warnings
from mt5_bridge import MT5Connector


def main() -> int:
    warnings.warn(
        "mt5_connector.py is deprecated. Use 'mt5-bridge' CLI or 'from mt5_bridge import MT5Connector'",
        DeprecationWarning,
        stacklevel=2,
    )
    connector = MT5Connector()
    ok = connector.connect()
    if not ok:
        print("Failed to initialize connector")
        return 1
    md = connector.get_market_data()
    if md:
        print(f"Market: {md.symbol} bid={md.bid} ask={md.ask} ts={md.timestamp}")
    else:
        print("Price file not found or invalid. Ensure EA is running and MT5_FILES_DIR is set.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


