#!/usr/bin/env python3
"""
MT5 File-Based Connector for Professional Forex Trading System
Handles all communication with MetaTrader 5 via shared JSON files.
"""

import json
import os
import time
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, asdict, field
import threading

from .config import get_config

logger = logging.getLogger(__name__)


@dataclass
class MarketData:
    """Market data structure"""
    symbol: str
    bid: float
    ask: float
    spread: float
    volume: int
    timestamp: int
    server_time: str

    @property
    def mid_price(self) -> float:
        """Calculate mid price"""
        return (self.bid + self.ask) / 2.0

    @property
    def spread_pips(self) -> float:
        """Calculate spread in pips (for XAUUSD: 1 pip = 0.1)"""
        if isinstance(self.symbol, str) and self.symbol.startswith("XAUUSD"):
            return self.spread * 10
        return self.spread

    @property
    def datetime(self) -> datetime:
        """Convert timestamp to datetime"""
        return datetime.fromtimestamp(self.timestamp)


@dataclass
class AccountInfo:
    """Account information structure"""
    balance: float
    equity: float
    margin: float
    free_margin: float
    profit: float
    leverage: int
    currency: str
    timestamp: int
    server_time: str

    @property
    def datetime(self) -> datetime:
        """Convert timestamp to datetime"""
        return datetime.fromtimestamp(self.timestamp)

    @property
    def margin_level(self) -> float:
        """Calculate margin level percentage"""
        if self.margin <= 0:
            return 0.0
        return (self.equity / self.margin) * 100


@dataclass
class TradeCommand:
    """Trade command structure"""
    action: str  # 'buy', 'sell', 'modify', or 'close'
    symbol: str
    lot_size: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    comment: str = ""
    magic_number: int = 12345
    timestamp: int = 0
    trade_id: Optional[str] = None
    ticket: Optional[int] = None  # For modify/close commands

    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = int(time.time())


@dataclass
class ModifyCommand:
    """Position modification command"""
    action: str = "modify"
    ticket: int = 0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    comment: str = ""
    timestamp: int = field(default_factory=lambda: int(time.time()))


@dataclass
class CloseCommand:
    """Position close command"""
    action: str = "close"
    ticket: int = 0
    close_volume: Optional[float] = None
    comment: str = ""
    timestamp: int = field(default_factory=lambda: int(time.time()))


@dataclass
class Position:
    """Open position structure"""
    ticket: int
    symbol: str
    type: str  # 'buy' or 'sell'
    volume: float
    price_open: float
    price_current: float
    sl: float
    tp: float
    profit: float
    swap: float
    magic: int
    comment: str
    time_open: str
    time_open_timestamp: int

    @property
    def open_datetime(self) -> datetime:
        """Convert open timestamp to datetime"""
        return datetime.fromtimestamp(self.time_open_timestamp)

    @property
    def formatted_profit(self) -> str:
        """Format profit with color indication"""
        return f"${self.profit:.2f}" if self.profit >= 0 else f"-${abs(self.profit):.2f}"

    @property
    def unrealized_pnl(self) -> float:
        """Get unrealized P&L including swap"""
        return self.profit + self.swap


@dataclass
class TradeResult:
    """Trade execution result"""
    action: str
    symbol: str
    result: str  # 'SUCCESS' or 'FAIL'
    timestamp: str
    order_id: Optional[int] = None
    price: Optional[float] = None
    error_message: Optional[str] = None
    trade_id: Optional[str] = None
    ticket: Optional[int] = None  # For modify/close results


@dataclass
class ClosedTrade:
    """Closed trade data structure"""
    ticket: int
    symbol: str
    type: str  # 'buy' or 'sell'
    volume: float
    entry_price: float
    exit_price: float
    sl: float
    tp: float
    profit: float
    change_percent: float
    close_time: str
    close_timestamp: int

    @property
    def close_datetime(self) -> datetime:
        """Convert close timestamp to datetime"""
        return datetime.fromtimestamp(self.close_timestamp)

    @property
    def formatted_profit(self) -> str:
        """Format profit with color indication"""
        return f"${self.profit:.2f}" if self.profit >= 0 else f"-${abs(self.profit):.2f}"

    @property
    def formatted_change(self) -> str:
        """Format change percentage"""
        return f"{self.change_percent:+.2f}%"


class ConnectionMonitor:
    """Monitor MT5 connection health via file timestamps"""

    def __init__(self, price_file_path: str):
        self.price_file_path = price_file_path
        self.config = get_config()
        self.is_monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.last_heartbeat = time.time()

    def start_monitoring(self):
        """Start connection monitoring in background thread"""
        if self.is_monitoring:
            return

        self.is_monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("Connection monitoring started")

    def stop_monitoring(self):
        """Stop connection monitoring"""
        self.is_monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("Connection monitoring stopped")

    def _monitor_loop(self):
        """Main monitoring loop"""
        timeout = self.config.get('mt5_bridge.connection_timeout_seconds', 30)

        while self.is_monitoring:
            try:
                price_file_path = self.price_file_path

                if os.path.exists(price_file_path):
                    file_mtime = os.path.getmtime(price_file_path)
                    time_since_update = time.time() - file_mtime

                    if time_since_update > timeout:
                        logger.warning(f"No price updates for {time_since_update:.1f} seconds")
                    else:
                        self.last_heartbeat = time.time()
                else:
                    logger.warning("Price file does not exist")

                time.sleep(5)

            except Exception as e:
                logger.error(f"Error in connection monitoring: {e}")
                time.sleep(10)


class MT5Connector:
    """
    Professional MT5 file-based connector.
    Handles all communication with MetaTrader 5 via shared JSON files.
    """

    def __init__(self):
        """Initialize MT5 connector"""
        self.config = get_config()
        self.connection_status = False
        self.last_price_data = None
        self.price_history: List[MarketData] = []
        self.trade_log_position = 0

        # File paths
        configured_dir = self.config.get_mt5_files_directory()

        # Determine primary symbol (used for tick/orderbook filenames). Fallback to XAUUSD.
        self.symbol = self.config.get('trading.primary_symbol', 'XAUUSD')

        # Respect config for price file if provided; otherwise build from symbol.
        price_file_from_cfg = self.config.get('mt5_bridge.price_file', None)
        if price_file_from_cfg:
            self.price_file_path = os.path.join(configured_dir, price_file_from_cfg)
        else:
            self.price_file_path = os.path.join(configured_dir, f"{self.symbol}_price.json")

        # If the configured/default price file does not exist, try to auto-resolve common broker aliases
        if not os.path.exists(self.price_file_path):
            resolved_path, resolved_symbol = self._auto_resolve_price_file(configured_dir, self.symbol)
            if resolved_path:
                self.price_file_path = resolved_path
                self.symbol = resolved_symbol or self.symbol
            else:
                # Try to find an alternate MT5 Files directory that contains a price file
                alt_dir, alt_price_path, alt_symbol = self._auto_resolve_files_dir_and_symbol(self.symbol)
                if alt_dir and alt_price_path:
                    configured_dir = alt_dir
                    self.price_file_path = alt_price_path
                    if alt_symbol:
                        self.symbol = alt_symbol

        # Persist resolved files directory
        self.files_dir = configured_dir

        self.command_file_path = os.path.join(self.files_dir, "commands.json")
        # Keep using EA's actual output file name for trade results
        self.trade_log_file_path = os.path.join(self.files_dir, "trade_results.txt")
        self.account_info_file_path = os.path.join(self.files_dir, "account_info.json")
        self.closed_trades_file_path = os.path.join(self.files_dir, "closed_trades.json")
        self.positions_file_path = os.path.join(self.files_dir, "positions.json")

        # Connection monitoring
        self.monitor = ConnectionMonitor(self.price_file_path)

        # If multiple price files exist, prefer the freshest one
        try:
            latest_path, latest_symbol = self._prefer_latest_price_file(self.files_dir, self.symbol)
            if latest_path and os.path.exists(latest_path) and latest_path != self.price_file_path:
                self.price_file_path = latest_path
                if latest_symbol:
                    self.symbol = latest_symbol
        except Exception as _e:
            logger.debug(f"prefer_latest check skipped: {_e}")

        logger.info("MT5 Connector initialized")
        logger.info(f"Price file: {self.price_file_path}")
        logger.info(f"Command file: {self.command_file_path}")
        logger.info(f"Trade log file: {self.trade_log_file_path}")
        logger.info(f"Account info file: {self.account_info_file_path}")
        logger.info(f"Closed trades file: {self.closed_trades_file_path}")
        logger.info(f"Positions file: {self.positions_file_path}")
        logger.info(f"Resolved primary symbol: {self.symbol}")
        logger.info(f"Files directory in use: {self.files_dir}")

    def connect(self) -> bool:
        """
        Establish connection to MT5 (verify files exist and are accessible)

        Returns:
            True if connection successful, False otherwise
        """
        try:
            logger.info("Connecting to MT5...")

            # Check if MT5 files directory exists
            mt5_dir = getattr(self, 'files_dir', self.config.get_mt5_files_directory())
            if not os.path.exists(mt5_dir):
                logger.error(f"MT5 files directory not found: {mt5_dir}")
                return False

            # Test price file access
            if os.path.exists(self.price_file_path):
                test_data = self.get_market_data()
                if test_data:
                    logger.info(f"✅ Price data available: {test_data.symbol} @ {test_data.bid}")
                    self.connection_status = True
                else:
                    logger.warning("Price file exists but contains invalid data")
            else:
                logger.warning("Price file does not exist yet")

            # Start connection monitoring
            self.monitor.start_monitoring()

            # Optionally skip historical trade log on first connect to avoid flooding
            try:
                skip_hist = self.config.get('mt5_bridge.skip_historical_trade_log_on_connect', True)
                if skip_hist and os.path.exists(self.trade_log_file_path):
                    self.trade_log_position = os.path.getsize(self.trade_log_file_path)
                    logger.info("Trade log set to EOF to skip historical entries on connect")
            except Exception as e:
                logger.debug(f"Unable to set trade log to EOF: {e}")

            logger.info("MT5 connection established")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to MT5: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from MT5 and cleanup resources"""
        logger.info("Disconnecting from MT5...")

        self.monitor.stop_monitoring()
        self.connection_status = False

        logger.info("MT5 disconnected")

    def is_connected(self) -> bool:
        """
        Check if connection to MT5 is active

        Returns:
            True if connected, False otherwise
        """
        return self.connection_status

    def get_market_data(self) -> Optional[MarketData]:
        """
        Get current market data from MT5

        Returns:
            MarketData object or None if error
        """
        try:
            if not os.path.exists(self.price_file_path):
                logger.debug("Price file does not exist")
                return None

            with open(self.price_file_path, 'r') as f:
                data = json.load(f)

            # Validate required fields
            required_fields = ['symbol', 'bid', 'ask', 'timestamp']
            if not all(field in data for field in required_fields):
                logger.warning("Price data missing required fields")
                return None

            market_data = MarketData(
                symbol=data['symbol'],
                bid=float(data['bid']),
                ask=float(data['ask']),
                spread=float(data.get('spread', data['ask'] - data['bid'])),
                volume=int(data.get('volume', 0)),
                timestamp=int(data['timestamp']),
                server_time=data.get('server_time', '')
            )

            # Update last price and history
            self.last_price_data = market_data
            self._update_price_history(market_data)

            return market_data

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Error parsing price data: {e}")
            return None
        except Exception as e:
            logger.error(f"Error reading market data: {e}")
            return None

    def _auto_resolve_price_file(self, mt5_dir: str, base_symbol: str) -> Tuple[Optional[str], Optional[str]]:
        """Try to find a price file for broker-specific symbol variants.

        Returns (resolved_path, resolved_symbol) or (None, None) if not found.
        """
        try:
            candidates: List[str] = []
            # Start with provided base
            candidates.append(f"{base_symbol}_price.json")
            # If missing broker suffix, try a common variant like '!'
            if '!' not in base_symbol:
                candidates.append(f"{base_symbol}!_price.json")
            else:
                # If base has '!' try without it
                candidates.append(f"{base_symbol.replace('!','')}_price.json")
            # Specific fallback for gold
            if base_symbol != 'XAUUSD':
                candidates.append("XAUUSD_price.json")
                candidates.append("XAUUSD!_price.json")

            # Check candidate files in order
            for fname in candidates:
                path = os.path.join(mt5_dir, fname)
                if os.path.exists(path):
                    resolved_symbol = fname.replace("_price.json", "")
                    logger.info(f"Auto-resolved price file: {path} (symbol {resolved_symbol})")
                    return path, resolved_symbol

            # As a last resort, scan for any *_price.json
            for fname in os.listdir(mt5_dir):
                if fname.endswith("_price.json"):
                    path = os.path.join(mt5_dir, fname)
                    resolved_symbol = fname.replace("_price.json", "")
                    logger.info(f"Auto-resolved by scan: {path} (symbol {resolved_symbol})")
                    return path, resolved_symbol
        except Exception as e:
            logger.debug(f"Auto-resolve price file failed: {e}")
        return None, None

    def _prefer_latest_price_file(self, mt5_dir: str, base_symbol: str) -> Tuple[Optional[str], Optional[str]]:
        """Among candidate symbol variants, pick the freshest _price.json file.

        Returns (path, symbol) or (None, None) if nothing found.
        """
        try:
            candidates: List[str] = []
            candidates.append(f"{base_symbol}_price.json")
            if '!' not in base_symbol:
                candidates.append(f"{base_symbol}!_price.json")
            else:
                candidates.append(f"{base_symbol.replace('!','')}_price.json")
            if base_symbol != 'XAUUSD':
                candidates.append("XAUUSD_price.json")
                candidates.append("XAUUSD!_price.json")

            existing: List[Tuple[float, str]] = []
            for fname in candidates:
                path = os.path.join(mt5_dir, fname)
                if os.path.exists(path):
                    try:
                        mtime = os.path.getmtime(path)
                        existing.append((mtime, path))
                    except Exception:
                        pass
            # If no candidate existed, scan for any *_price.json and pick newest
            if not existing:
                for fname in os.listdir(mt5_dir):
                    if fname.endswith("_price.json"):
                        path = os.path.join(mt5_dir, fname)
                        try:
                            mtime = os.path.getmtime(path)
                            existing.append((mtime, path))
                        except Exception:
                            pass
            if not existing:
                return None, None
            existing.sort(reverse=True)
            _, best_path = existing[0]
            best_symbol = os.path.basename(best_path).replace("_price.json", "")
            return best_path, best_symbol
        except Exception as e:
            logger.debug(f"prefer_latest failed: {e}")
            return None, None

    def _auto_resolve_files_dir_and_symbol(self, base_symbol: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Search for alternate MT5 Files directories that contain *_price.json.

        Returns (resolved_dir, price_file_path, symbol) or (None, None, None).
        """
        try:
            # Heuristics: look in common relative paths from current working dir
            candidates_dirs = [
                os.getcwd(),
                os.path.expanduser("~"),
            ]
            for d in candidates_dirs:
                try:
                    for fname in os.listdir(d):
                        if fname.endswith("_price.json"):
                            path = os.path.join(d, fname)
                            symbol = fname.replace("_price.json", "")
                            return d, path, symbol
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"Auto-resolve files dir failed: {e}")
        return None, None, None

    def _update_price_history(self, market_data: MarketData) -> None:
        """Update price history with new data"""
        # Add to history
        self.price_history.append(market_data)

        # Keep only last 1000 records
        if len(self.price_history) > 1000:
            self.price_history = self.price_history[-1000:]

    def get_price_history(self, limit: int = 100) -> List[MarketData]:
        """
        Get recent price history

        Args:
            limit: Maximum number of records to return

        Returns:
            List of MarketData objects
        """
        return self.price_history[-limit:]

    def _write_command(self, command_dict: Dict[str, Any]) -> bool:
        """
        Write command to MT5 command file

        Args:
            command_dict: Dictionary containing command data

        Returns:
            True if command written successfully, False otherwise
        """
        try:
            # Write command to file (compact JSON format for EA compatibility)
            with open(self.command_file_path, 'w') as f:
                json.dump(command_dict, f, separators=(',', ':'))

            logger.info(f"➡️ Command sent: {command_dict.get('action', 'unknown').upper()}")
            return True

        except Exception as e:
            logger.error(f"Error writing command: {e}")
            return False

    def send_trade_command(self, command: TradeCommand) -> bool:
        """
        Send trade command to MT5

        Args:
            command: TradeCommand object

        Returns:
            True if command sent successfully, False otherwise
        """
        try:
            # Validate command
            if command.action not in ['buy', 'sell', 'modify', 'close']:
                logger.error(f"Invalid trade action: {command.action}")
                return False

            if command.action in ['buy', 'sell'] and command.lot_size <= 0:
                logger.error(f"Invalid lot size: {command.lot_size}")
                return False

            if command.action in ['modify', 'close'] and not command.ticket:
                logger.error(f"Ticket required for {command.action} command")
                return False

            # Normalize symbol to resolved primary symbol for this broker (prevents XAUUSD vs XAUUSD! mismatch)
            try:
                if command.action in ['buy', 'sell']:
                    broker_symbol = getattr(self, 'symbol', None)
                    if broker_symbol and command.symbol != broker_symbol:
                        logger.info(f"Normalizing trade symbol: {command.symbol} -> {broker_symbol}")
                        command.symbol = broker_symbol
            except Exception:
                pass

            # Convert to dictionary
            command_dict = asdict(command)

            return self._write_command(command_dict)

        except Exception as e:
            logger.error(f"Error sending trade command: {e}")
            return False

    def place_buy_order(self, symbol: str, lot_size: float,
                        stop_loss: Optional[float] = None,
                        take_profit: Optional[float] = None,
                        comment: str = "",
                        trade_id: Optional[str] = None) -> bool:
        """
        Place a buy order

        Args:
            symbol: Trading symbol
            lot_size: Position size
            stop_loss: Stop loss price (optional)
            take_profit: Take profit price (optional)
            comment: Order comment (optional)

        Returns:
            True if order placed successfully, False otherwise
        """
        command = TradeCommand(
            action='buy',
            symbol=symbol,
            lot_size=lot_size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            comment=comment,
            trade_id=trade_id
        )

        return self.send_trade_command(command)

    def place_sell_order(self, symbol: str, lot_size: float,
                         stop_loss: Optional[float] = None,
                         take_profit: Optional[float] = None,
                         comment: str = "",
                         trade_id: Optional[str] = None) -> bool:
        """
        Place a sell order

        Args:
            symbol: Trading symbol
            lot_size: Position size
            stop_loss: Stop loss price (optional)
            take_profit: Take profit price (optional)
            comment: Order comment (optional)

        Returns:
            True if order placed successfully, False otherwise
        """
        command = TradeCommand(
            action='sell',
            symbol=symbol,
            lot_size=lot_size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            comment=comment,
            trade_id=trade_id
        )

        return self.send_trade_command(command)

    def modify_order(self, ticket: int,
                     stop_loss: Optional[float] = None,
                     take_profit: Optional[float] = None,
                     comment: str = "") -> bool:
        """
        Modify an existing position's stop loss and/or take profit

        Args:
            ticket: Position ticket number
            stop_loss: New stop loss price (optional)
            take_profit: New take profit price (optional)
            comment: Modification comment (optional)

        Returns:
            True if modification sent successfully, False otherwise
        """
        command = ModifyCommand(
            ticket=ticket,
            stop_loss=stop_loss,
            take_profit=take_profit,
            comment=comment
        )

        command_dict = asdict(command)
        return self._write_command(command_dict)

    def close_position(self, ticket: int, comment: str = "", volume: Optional[float] = None) -> bool:
        """
        Close an existing position, optionally partially

        Args:
            ticket: Position ticket number
            comment: Close comment (optional)
            volume: If provided and less than current, performs partial close

        Returns:
            True if close command sent successfully, False otherwise
        """
        command = CloseCommand(
            ticket=ticket,
            comment=comment,
            close_volume=volume
        )

        command_dict = asdict(command)
        return self._write_command(command_dict)

    def get_trade_results(self) -> List[TradeResult]:
        """
        Get new trade results from MT5

        Returns:
            List of TradeResult objects
        """
        try:
            if not os.path.exists(self.trade_log_file_path):
                return []
            results = []
            with open(self.trade_log_file_path, 'r') as f:
                f.seek(self.trade_log_position)
                new_lines = f.readlines()
                self.trade_log_position = f.tell()
            for line in new_lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    # Parse log line format: "2025.07.29 17:05 | action | SUCCESS | details | XAUUSD | trade_id"
                    parts = line.split(' | ')
                    if len(parts) >= 6:
                        timestamp = parts[0].strip()
                        action = parts[1].strip()
                        result = parts[2].strip()
                        details = parts[3].strip()
                        symbol = parts[4].strip()
                        trade_id = parts[5].strip()

                        trade_result = TradeResult(
                            action=action,
                            symbol=symbol,
                            result=result,
                            timestamp=timestamp,
                            order_id=None,
                            price=None,
                            error_message=None,
                            trade_id=trade_id
                        )

                        # Parse ticket from details for modify/close actions
                        if action in ['modify', 'close'] and 'ticket:' in details:
                            try:
                                ticket_str = details.split('ticket:')[1].strip()
                                trade_result.ticket = int(ticket_str)
                            except (ValueError, IndexError):
                                pass

                        results.append(trade_result)
                    elif len(parts) >= 3:
                        # Fallback for old format
                        timestamp = parts[0].strip()
                        action = parts[1].strip()
                        result = parts[2].strip()
                        trade_result = TradeResult(
                            action=action,
                            symbol=self.config.get('trading.primary_symbol', 'XAUUSD'),
                            result=result,
                            timestamp=timestamp
                        )
                        results.append(trade_result)
                except Exception as e:
                    logger.warning(f"Error parsing trade log line '{line}': {e}")
                    continue
            return results
        except Exception as e:
            logger.error(f"Error reading trade results: {e}")
            return []

    def get_positions(self) -> List[Position]:
        """
        Get current open positions from MT5

        Returns:
            List of Position objects
        """
        try:
            if not os.path.exists(self.positions_file_path):
                logger.debug("Positions file does not exist")
                return []

            with open(self.positions_file_path, 'r') as f:
                data = json.load(f)

            # Check if data has the expected structure
            if 'positions' not in data:
                logger.warning("Positions file missing 'positions' field")
                return []

            positions = []
            for pos_data in data['positions']:
                try:
                    # Validate required fields
                    required_fields = ['ticket', 'symbol', 'type', 'volume', 'price_open',
                                       'price_current', 'profit', 'time_open_timestamp']

                    if not all(field in pos_data for field in required_fields):
                        logger.warning(f"Position data missing required fields: {pos_data}")
                        continue

                    position = Position(
                        ticket=int(pos_data['ticket']),
                        symbol=pos_data['symbol'],
                        type=pos_data['type'],
                        volume=float(pos_data['volume']),
                        price_open=float(pos_data['price_open']),
                        price_current=float(pos_data['price_current']),
                        sl=float(pos_data.get('sl', 0)),
                        tp=float(pos_data.get('tp', 0)),
                        profit=float(pos_data['profit']),
                        swap=float(pos_data.get('swap', 0)),
                        magic=int(pos_data.get('magic', 0)),
                        comment=pos_data.get('comment', ''),
                        time_open=pos_data['time_open'],
                        time_open_timestamp=int(pos_data['time_open_timestamp'])
                    )

                    positions.append(position)

                except (ValueError, KeyError) as e:
                    logger.warning(f"Error parsing position data: {e}")
                    continue

            logger.debug(f"Retrieved {len(positions)} open positions")
            return positions

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Error parsing positions data: {e}")
            return []
        except Exception as e:
            logger.error(f"Error reading positions: {e}")
            return []

    def get_trade_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get trading history from MT5 trade results file

        Args:
            limit: Maximum number of recent trades to return

        Returns:
            List of trade dictionaries with historical data
        """
        try:
            history_file = os.path.join(getattr(self, 'files_dir', self.config.get_mt5_files_directory()), "trade_results.txt")

            if not os.path.exists(history_file):
                logger.debug("Trade results file does not exist")
                return []

            trades = []
            with open(history_file, 'r') as f:
                lines = f.readlines()

            # Parse each line (format: "2025.07.31 18:56 | sell | SUCCESS | 0.02 | XAUUSD | trade_id")
            for line in reversed(lines[-limit:]):  # Get most recent trades first
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                try:
                    parts = line.split(' | ')
                    if len(parts) >= 5:
                        timestamp = parts[0].strip()
                        action = parts[1].strip()
                        result = parts[2].strip()
                        lot_size = float(parts[3].strip())
                        symbol = parts[4].strip()
                        trade_id = parts[5].strip() if len(parts) > 5 else "N/A"

                        # Convert timestamp to more readable format
                        try:
                            dt = datetime.strptime(timestamp, '%Y.%m.%d %H:%M')
                            formatted_time = dt.strftime('%m/%d %H:%M')
                        except Exception:
                            formatted_time = timestamp

                        trade = {
                            'timestamp': timestamp,
                            'formatted_time': formatted_time,
                            'action': action,
                            'result': result,
                            'lot_size': lot_size,
                            'symbol': symbol,
                            'trade_id': trade_id
                        }
                        trades.append(trade)

                except Exception as e:
                    logger.warning(f"Error parsing trade history line '{line}': {e}")
                    continue

            return trades

        except Exception as e:
            logger.error(f"Error reading trade history: {e}")
            return []

    def get_account_info(self) -> Optional[AccountInfo]:
        """
        Get current account information from MT5

        Returns:
            AccountInfo object or None if error
        """
        try:
            if not os.path.exists(self.account_info_file_path):
                logger.debug("Account info file does not exist")
                return None

            with open(self.account_info_file_path, 'r') as f:
                data = json.load(f)

            # Validate required fields
            required_fields = ['balance', 'equity', 'margin', 'free_margin', 'profit']
            if not all(field in data for field in required_fields):
                logger.warning("Account info missing required fields")
                return None

            account_info = AccountInfo(
                balance=float(data['balance']),
                equity=float(data['equity']),
                margin=float(data.get('margin', 0)),
                free_margin=float(data['free_margin']),
                profit=float(data['profit']),
                leverage=int(data.get('leverage', 100)),
                currency=data.get('currency', 'USD'),
                timestamp=int(data.get('timestamp', time.time())),
                server_time=data.get('server_time', '')
            )

            return account_info

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Error parsing account info: {e}")
            return None
        except Exception as e:
            logger.error(f"Error reading account info: {e}")
            return None

    def get_closed_trades(self, limit: int = 1000) -> List[ClosedTrade]:
        """
        Get recent closed trades from MT5

        Args:
            limit: Maximum number of trades to return

        Returns:
            List of ClosedTrade objects
        """
        try:
            if not os.path.exists(self.closed_trades_file_path):
                logger.debug("Closed trades file does not exist")
                return []

            with open(self.closed_trades_file_path, 'r') as f:
                data = json.load(f)

            # Check if data has the expected structure
            if 'trades' not in data:
                logger.warning("Closed trades file missing 'trades' field")
                return []

            trades = []
            for trade_data in data['trades'][:limit]:
                try:
                    # Validate required fields
                    required_fields = ['ticket', 'symbol', 'type', 'volume', 'entry_price',
                                       'exit_price', 'profit', 'change_percent', 'close_time', 'close_timestamp']

                    if not all(field in trade_data for field in required_fields):
                        logger.warning(f"Trade data missing required fields: {trade_data}")
                        continue

                    closed_trade = ClosedTrade(
                        ticket=int(trade_data['ticket']),
                        symbol=trade_data['symbol'],
                        type=trade_data['type'],
                        volume=float(trade_data['volume']),
                        entry_price=float(trade_data['entry_price']),
                        exit_price=float(trade_data['exit_price']),
                        sl=float(trade_data.get('sl', 0)),
                        tp=float(trade_data.get('tp', 0)),
                        profit=float(trade_data['profit']),
                        change_percent=float(trade_data['change_percent']),
                        close_time=trade_data['close_time'],
                        close_timestamp=int(trade_data['close_timestamp'])
                    )

                    trades.append(closed_trade)

                except (ValueError, KeyError) as e:
                    logger.warning(f"Error parsing trade data: {e}")
                    continue

            logger.debug(f"Retrieved {len(trades)} closed trades")
            return trades

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Error parsing closed trades data: {e}")
            return []
        except Exception as e:
            logger.error(f"Error reading closed trades: {e}")
            return []

    def get_connection_info(self) -> Dict[str, Any]:
        """
        Get connection status and statistics

        Returns:
            Dictionary with connection information
        """
        return {
            'connected': self.connection_status,
            'last_price_update': self.last_price_data.datetime if self.last_price_data else None,
            'price_history_count': len(self.price_history),
            'files_directory': getattr(self, 'files_dir', self.config.get_mt5_files_directory()),
            'price_file_exists': os.path.exists(self.price_file_path),
            'command_file_exists': os.path.exists(self.command_file_path),
            'trade_log_file_exists': os.path.exists(self.trade_log_file_path),
            'positions_file_exists': os.path.exists(self.positions_file_path),
            'last_heartbeat': datetime.fromtimestamp(self.monitor.last_heartbeat)
        }

    def clear_command_file(self) -> bool:
        """
        Clear the command file (useful for cleanup)

        Returns:
            True if successful, False otherwise
        """
        try:
            if os.path.exists(self.command_file_path):
                with open(self.command_file_path, 'w') as f:
                    f.write('')
                logger.debug("Command file cleared")
            return True
        except Exception as e:
            logger.error(f"Error clearing command file: {e}")
            return False

    def test_connection(self) -> Tuple[bool, str]:
        """
        Test MT5 connection and return detailed status

        Returns:
            Tuple of (success, status_message)
        """
        try:
            # Check files directory
            mt5_dir = self.config.get_mt5_files_directory()
            if not os.path.exists(mt5_dir):
                return False, f"MT5 files directory not found: {mt5_dir}"

            # Check price file
            if not os.path.exists(self.price_file_path):
                return False, "Price file not found - ensure MT5 EA is running"

            # Try to read price data
            market_data = self.get_market_data()
            if not market_data:
                return False, "Unable to parse price data"

            # Check data freshness
            data_age = time.time() - market_data.timestamp
            if data_age > 60:  # 1 minute
                return False, f"Price data is stale ({data_age:.1f} seconds old)"

            return True, f"Connection OK - {market_data.symbol} @ {market_data.bid}"

        except Exception as e:
            return False, f"Connection test failed: {e}"

    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()

    def get_tick_data(self) -> Dict[str, Any]:
        """
        Get enhanced tick data from MQ5 v4.0

        Returns:
            Dict with enhanced tick information
        """
        try:
            symbol = getattr(self, 'symbol', 'XAUUSD')
            tick_file = os.path.join(getattr(self, 'files_dir', self.config.get_mt5_files_directory()), f"{symbol}_tick.json")

            if os.path.exists(tick_file):
                with open(tick_file, 'r') as f:
                    tick_data = json.load(f)

                logger.debug(f"Tick data retrieved: {tick_data}")
                return tick_data
            else:
                logger.warning(f"Tick file not found: {tick_file}")
                return {}

        except Exception as e:
            logger.error(f"Error reading tick data: {e}")
            return {}

    def get_order_book(self) -> Dict[str, Any]:
        """
        Get order book/depth of market data from MQ5 v4.0

        Returns:
            Dict with order book information
        """
        try:
            symbol = getattr(self, 'symbol', 'XAUUSD')
            orderbook_file = os.path.join(getattr(self, 'files_dir', self.config.get_mt5_files_directory()), f"{symbol}_orderbook.json")

            if os.path.exists(orderbook_file):
                with open(orderbook_file, 'r') as f:
                    orderbook_data = json.load(f)

                logger.debug(f"Order book data retrieved: {len(orderbook_data.get('levels', []))} levels")
                return orderbook_data
            else:
                logger.warning(f"Order book file not found: {orderbook_file}")
                return {}

        except Exception as e:
            logger.error(f"Error reading order book data: {e}")
            return {}

    def get_symbol_info(self) -> Dict[str, Any]:
        """
        Get symbol specifications from MQ5 v4.0

        Returns:
            Dict with symbol specifications
        """
        try:
            symbol_file = os.path.join(getattr(self, 'files_dir', self.config.get_mt5_files_directory()), "symbol_info.json")

            if os.path.exists(symbol_file):
                with open(symbol_file, 'r') as f:
                    symbol_data = json.load(f)

                logger.debug(f"Symbol info retrieved for {symbol_data.get('symbol', 'Unknown')}")
                return symbol_data
            else:
                logger.warning(f"Symbol info file not found: {symbol_file}")
                return {}

        except Exception as e:
            logger.error(f"Error reading symbol info: {e}")
            return {}

    def get_pending_orders(self) -> List[Dict[str, Any]]:
        """
        Get pending orders from MQ5 v4.0

        Returns:
            List of pending orders
        """
        try:
            orders_file = os.path.join(getattr(self, 'files_dir', self.config.get_mt5_files_directory()), "orders.json")

            if os.path.exists(orders_file):
                with open(orders_file, 'r') as f:
                    orders_data = json.load(f)

                orders = orders_data.get('orders', [])
                logger.debug(f"Retrieved {len(orders)} pending orders")
                return orders
            else:
                logger.warning(f"Orders file not found: {orders_file}")
                return []

        except Exception as e:
            logger.error(f"Error reading pending orders: {e}")
            return []

    def get_rates_m1(self) -> Dict[str, Any]:
        """
        Get compact M1 OHLCV history exported by the EA (rates_M1.json)

        Returns:
            Dict with keys: symbol, timeframe, bars (list of OHLCV objects)
        """
        try:
            rates_file = os.path.join(getattr(self, 'files_dir', self.config.get_mt5_files_directory()), "rates_M1.json")

            if os.path.exists(rates_file):
                with open(rates_file, 'r') as f:
                    data = json.load(f)
                # Minimal validation
                if isinstance(data, dict) and 'bars' in data:
                    logger.debug(f"Rates M1 retrieved: {len(data.get('bars', []))} bars")
                    return data
                else:
                    logger.warning("rates_M1.json has unexpected structure")
                    return {}
            else:
                logger.warning(f"Rates file not found: {rates_file}")
                return {}
        except Exception as e:
            logger.error(f"Error reading rates M1 data: {e}")
            return {}

    def __str__(self) -> str:
        """String representation"""
        status = "Connected" if self.connection_status else "Disconnected"
        return f"MT5Connector(status={status}, last_price={self.last_price_data.bid if self.last_price_data else 'N/A'})"


# Global connector instance
_connector_instance: Optional[MT5Connector] = None


def get_connector() -> MT5Connector:
    """Get global MT5 connector instance (singleton pattern)"""
    global _connector_instance
    if _connector_instance is None:
        _connector_instance = MT5Connector()
    return _connector_instance


