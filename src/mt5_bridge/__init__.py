"""mt5_bridge package

High-level, file-based connector for MetaTrader 5 on macOS.

Public API:
- MT5Connector
- get_connector
"""

from .connector import (
    MT5Connector,
    MarketData,
    AccountInfo,
    Position,
    TradeCommand,
    TradeResult,
    ClosedTrade,
    get_connector,
)

__version__ = "0.1.0"

__all__ = [
    "MT5Connector",
    "MarketData",
    "AccountInfo",
    "Position",
    "TradeCommand",
    "TradeResult",
    "ClosedTrade",
    "get_connector",
    "__version__",
]


