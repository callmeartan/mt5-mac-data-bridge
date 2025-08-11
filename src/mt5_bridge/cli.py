import argparse
import logging
import os
from .connector import MT5Connector


def main() -> int:
    parser = argparse.ArgumentParser(description="MT5 macOS file bridge CLI")
    parser.add_argument("--files-dir", help="Path to MT5 MQL5/Files directory (overrides MT5_FILES_DIR)")
    parser.add_argument("--symbol", help="Primary symbol (overrides MT5_PRIMARY_SYMBOL)")
    parser.add_argument("--log-level", default="INFO", help="Logging level (DEBUG, INFO, WARNING, ERROR)")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.files_dir:
        os.environ["MT5_FILES_DIR"] = args.files_dir
    if args.symbol:
        os.environ["MT5_PRIMARY_SYMBOL"] = args.symbol

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

    info = connector.get_connection_info()
    print("Connection info:", {
        "files_directory": info.get("files_directory"),
        "price_file_exists": info.get("price_file_exists"),
        "positions_file_exists": info.get("positions_file_exists"),
    })
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


