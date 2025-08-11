from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class BridgeConfig:
    """Simple configuration accessor for the MT5 bridge.

    Values are read from environment variables with reasonable defaults.
    """

    def get(self, key: str, default: Any = None) -> Any:
        mapping = {
            "mt5_bridge.connection_timeout_seconds": ("MT5_TIMEOUT_SEC", default),
            "mt5_bridge.price_file": ("MT5_PRICE_FILE", default),
            "trading.primary_symbol": ("MT5_PRIMARY_SYMBOL", default),
            "mt5_bridge.skip_historical_trade_log_on_connect": ("MT5_SKIP_HIST_LOG", default),
        }
        env_key, fallback = mapping.get(key, (None, default))
        if env_key is None:
            return default
        if env_key == "MT5_TIMEOUT_SEC":
            value = os.getenv(env_key)
            if value is None:
                return fallback if fallback is not None else 30
            try:
                return int(value)
            except ValueError:
                return 30
        if env_key == "MT5_SKIP_HIST_LOG":
            value = os.getenv(env_key)
            if value is None:
                return True if fallback is None else bool(fallback)
            return value.lower() in {"1", "true", "yes"}
        return os.getenv(env_key, fallback)

    def get_mt5_files_directory(self) -> str:
        """Resolve the MT5 `MQL5/Files` directory.

        Priority:
        - MT5_FILES_DIR env var
        - examples/path.hint.txt (if present)
        - current directory
        """
        env_path = os.getenv("MT5_FILES_DIR")
        if env_path:
            return env_path
        # Use hint if provided
        hint_file = Path("examples/path.hint.txt")
        if hint_file.exists():
            try:
                content = hint_file.read_text().strip()
                # Only accept if it's an existing directory path
                if content and os.path.isabs(content) and os.path.isdir(content):
                    return content
            except Exception:
                pass
        return str(Path.cwd())


def get_config() -> BridgeConfig:
    return BridgeConfig()


