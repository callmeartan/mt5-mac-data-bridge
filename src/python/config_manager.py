"""
Minimal configuration manager for the MT5 Mac File Bridge.

This keeps the open-source bridge self-contained without exposing any
private app code. It reads configuration primarily from environment
variables and exposes a tiny API used by `bridge_app.py`:

- get(key: str, default)
- get_mt5_files_directory() -> str

Environment variables:
- MT5_FILES_DIR: Absolute path to the MT5 DataFolder's MQL5/Files directory
- MT5_PRIMARY_SYMBOL: Preferred trading symbol (default: XAUUSD)
- MT5_PRICE_FILE: Optional explicit price file name (e.g., XAUUSD!_price.json)
- MT5_TIMEOUT_SEC: Connection heartbeat timeout in seconds (default: 30)
"""

from __future__ import annotations

import os
from typing import Any, Optional


class _SimpleConfig:
    def __init__(self) -> None:
        # Flat key-value store; dot keys are supported directly
        timeout_value = os.environ.get("MT5_TIMEOUT_SEC", "30")
        try:
            timeout_seconds = int(timeout_value)
        except ValueError:
            timeout_seconds = 30

        self._data: dict[str, Any] = {
            "trading.primary_symbol": os.environ.get("MT5_PRIMARY_SYMBOL", "XAUUSD"),
            "mt5_bridge.price_file": os.environ.get("MT5_PRICE_FILE", None),
            "mt5_bridge.skip_historical_trade_log_on_connect": True,
            "mt5_bridge.connection_timeout_seconds": timeout_seconds,
        }

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        return self._data.get(key, default)

    def get_mt5_files_directory(self) -> str:
        # Prefer explicit environment variable
        env_path = os.environ.get("MT5_FILES_DIR")
        if env_path:
            return env_path

        # Fallback: current working directory. This keeps the bridge functional
        # for read-only operations where files are colocated.
        return os.getcwd()


_CONFIG_SINGLETON: Optional[_SimpleConfig] = None


def get_config() -> _SimpleConfig:
    global _CONFIG_SINGLETON
    if _CONFIG_SINGLETON is None:
        _CONFIG_SINGLETON = _SimpleConfig()
    return _CONFIG_SINGLETON


__all__ = ["get_config"]


