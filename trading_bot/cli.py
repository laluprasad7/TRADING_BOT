#!/usr/bin/env python3
"""
cli.py – PrimeTrade CLI entry point.

Two modes:

  1. **Direct mode** (all args on command line) ::

        python cli.py --symbol BTCUSDT --side BUY --type MARKET --qty 0.001

  2. **Interactive mode** (no required args → guided menu) ::

        python cli.py

Environment variables (or ``.env`` file):
  BINANCE_API_KEY    – Your Binance Futures Testnet API key.
  BINANCE_API_SECRET – Your Binance Futures Testnet API secret.
  BINANCE_BASE_URL   – Override base URL (default: testnet).
  LOG_DIR            – Directory for log files (default: ./logs).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import textwrap
from pathlib import Path
from typing import Optional

# ── Optional .env support ─────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; rely on real env vars

# ── Internal imports ──────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from bot.logging_config import setup_logging
from bot.client import BinanceFuturesClient, APIError, NetworkError
from bot.orders import OrderManager
from bot.validators import (
    validate_symbol,
    validate_side,
    validate_order_type,
    validate_quantity,
    validate_price,
    validate_time_in_force,
    get_symbol_filters,
    VALID_ORDER_TYPES,
    VALID_SIDES,
    VALID_TIF,
)

# ---------------------------------------------------------------------------
# Constants / helpers
# ---------------------------------------------------------------------------

BANNER = r"""
 ____       _          _____              _
|  _ \ _ __(_)_ __ ___|_   _| __ __ _  __| | ___
| |_) | '__| | '_ ` _ \ | || '__/ _` |/ _` |/ _ \
|  __/| |  | | | | | | || || | | (_| | (_| |  __/
|_|   |_|  |_|_| |_| |_||_||_|  \__,_|\__,_|\___|
   Binance Futures Testnet  •  USDT-M  •  v1.0.0
"""

_COLOURS = {
    "reset":   "\033[0m",
    "bold":    "\033[1m",
    "cyan":    "\033[36m",
    "green":   "\033[32m",
    "yellow":  "\033[33m",
    "red":     "\033[31m",
    "magenta": "\033[35m",
    "blue":    "\033[34m",
}

def _c(text: str, colour: str) -> str:
    """Wrap *text* in ANSI colour escapes (skipped when not a tty)."""
    if not sys.stdout.isatty():
        return text
    return f"{_COLOURS.get(colour, '')}{text}{_COLOURS['reset']}"


def _println(msg: str = "", colour: str = "") -> None:
    print(_c(msg, colour) if colour else msg)


def _hr(char: str = "─", width: int = 54, colour: str = "cyan") -> None:
    _println(char * width, colour)


def _success(msg: str) -> None:
    _println(f"  ✔  {msg}", "green")


def _warn(msg: str) -> None:
    _println(f"  ⚠  {msg}", "yellow")


def _error(msg: str) -> None:
    _println(f"  ✘  {msg}", "red")


def _prompt(question: str, default: str = "") -> str:
    """Show *question* and read input; return *default* on empty input."""
    default_hint = f" [{default}]" if default else ""
    try:
        answer = input(_c(f"  ➜  {question}{default_hint}: ", "cyan")).strip()
    except (EOFError, KeyboardInterrupt):
        _println("\nAborted.", "yellow")
        sys.exit(0)
    return answer or default


def _prompt_choice(question: str, choices: list[str], default: str = "") -> str:
    """Prompt with a list of choices until a valid one is entered."""
    opts = " / ".join(
        _c(c, "bold") if c == default else c for c in choices
    )
    while True:
        val = _prompt(f"{question} ({opts})", default).strip().upper()
        if val in [c.upper() for c in choices]:
            return val
        _error(f"Invalid choice. Please enter one of: {', '.join(choices)}")


logger = logging.getLogger("primetrade.cli")


# ---------------------------------------------------------------------------
# Core workflow
# ---------------------------------------------------------------------------

def _load_credentials() -> tuple[str, str, str]:
    """Read API credentials from environment.

    Returns:
        (api_key, api_secret, base_url)

    Exits if credentials are missing.
    """
    key    = os.getenv("BINANCE_API_KEY",    "").strip()
    secret = os.getenv("BINANCE_API_SECRET", "").strip()
    url    = os.getenv(
        "BINANCE_BASE_URL",
        "https://testnet.binancefuture.com",
    ).strip()

    if not key or not secret:
        _error(
            "API credentials not found.\n"
            "  Set BINANCE_API_KEY and BINANCE_API_SECRET in your environment\n"
            "  or in a .env file in the project root."
        )
        sys.exit(1)

    return key, secret, url


def _build_client_and_manager(
    api_key: str,
    api_secret: str,
    base_url: str,
    symbol: str,
) -> tuple[BinanceFuturesClient, OrderManager, dict]:
    """Instantiate client, fetch exchange info, validate symbol.

    Returns:
        (client, order_manager, exchange_info)
    """
    client = BinanceFuturesClient(api_key, api_secret, base_url)

    _println("  Fetching exchange info …", "cyan")
    try:
        exchange_info = client.get_exchange_info()
    except (APIError, NetworkError) as exc:
        _error(f"Failed to fetch exchange info: {exc}")
        logger.exception("Failed to fetch exchange info")
        sys.exit(1)

    manager = OrderManager(client, exchange_info)
    return client, manager, exchange_info


def _print_order_summary(
    symbol: str,
    side: str,
    order_type: str,
    quantity: str,
    price: Optional[str] = None,
    stop_price: Optional[str] = None,
    time_in_force: Optional[str] = None,
) -> None:
    """Print a formatted order request summary."""
    _hr()
    _println("  ORDER REQUEST SUMMARY", "bold")
    _hr()
    _println(f"  Symbol        : {_c(symbol, 'bold')}")
    _println(f"  Side          : {_c(side, 'green' if side == 'BUY' else 'red')}")
    _println(f"  Type          : {_c(order_type, 'magenta')}")
    _println(f"  Quantity      : {quantity}")
    if price:
        _println(f"  Limit Price   : {price}")
    if stop_price:
        _println(f"  Stop Price    : {stop_price}")
    if time_in_force:
        _println(f"  Time-in-Force : {time_in_force}")
    _hr()


def _place_and_display(
    manager: OrderManager,
    order_type: str,
    symbol: str,
    side: str,
    quantity: str,
    price: Optional[str] = None,
    stop_price: Optional[str] = None,
    time_in_force: str = "GTC",
) -> None:
    """Place an order and print the response. Handles exceptions cleanly."""
    try:
        if order_type == "MARKET":
            response = manager.place_market(symbol, side, quantity)
        elif order_type == "LIMIT":
            response = manager.place_limit(symbol, side, quantity, price, time_in_force)
        elif order_type in {"STOP_LIMIT", "STOP"}:
            response = manager.place_stop_limit(
                symbol, side, quantity, stop_price, price, time_in_force
            )
        else:
            _error(f"Unsupported order type: {order_type}")
            return

    except ValueError as exc:
        _error(f"Validation error: {exc}")
        logger.error("Validation error: %s", exc)
        return
    except APIError as exc:
        _error(f"Binance API error: {exc}")
        logger.error("APIError: %s", exc, exc_info=True)
        return
    except NetworkError as exc:
        _error(f"Network error: {exc}")
        logger.error("NetworkError: %s", exc, exc_info=True)
        return

    _println()
    _println("  ORDER RESPONSE", "bold")
    _println(manager.format_order_response(response))
    _success("Order placed successfully!")
    _println()


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------

def interactive_mode(
    client: BinanceFuturesClient,
    manager: OrderManager,
    exchange_info: dict,
) -> None:
    """Interactive guided menu."""
    _println(BANNER, "cyan")
    _println("  Welcome to PrimeTrade – Binance Futures Testnet", "bold")
    _println()

    while True:
        _hr("═")
        _println("  MAIN MENU", "bold")
        _hr("═")
        _println("  1) Place a new order")
        _println("  2) View account balance")
        _println("  3) Exit")
        _hr()
        choice = _prompt("Select option", "1")

        if choice == "1":
            _place_order_interactive(manager, exchange_info)
        elif choice == "2":
            _show_balance(client)
        elif choice in {"3", "q", "quit", "exit"}:
            _println("\n  Goodbye! 👋", "cyan")
            break
        else:
            _warn("Invalid option. Please enter 1, 2, or 3.")


def _place_order_interactive(
    manager: OrderManager,
    exchange_info: dict,
) -> None:
    """Walk the user through all order fields interactively."""
    _println()
    _println("  ── New Order ──────────────────────────────────────", "cyan")

    # ── Symbol ────────────────────────────────────────────────────────────
    while True:
        raw_symbol = _prompt("Symbol (e.g. BTCUSDT)", "BTCUSDT")
        try:
            symbol = validate_symbol(raw_symbol, exchange_info)
            break
        except ValueError as exc:
            _error(str(exc))

    # ── Side ──────────────────────────────────────────────────────────────
    side = _prompt_choice("Side", ["BUY", "SELL"], "BUY")

    # ── Order type ────────────────────────────────────────────────────────
    order_type = _prompt_choice(
        "Order type", ["MARKET", "LIMIT", "STOP_LIMIT"], "MARKET"
    )

    # ── Quantity ──────────────────────────────────────────────────────────
    filters = get_symbol_filters(symbol, exchange_info)
    while True:
        raw_qty = _prompt("Quantity (base asset)")
        try:
            quantity = validate_quantity(raw_qty, filters)
            break
        except ValueError as exc:
            _error(str(exc))

    # ── Price / stop price ────────────────────────────────────────────────
    price       = None
    stop_price  = None
    time_in_force = "GTC"

    if order_type in {"LIMIT", "STOP_LIMIT"}:
        while True:
            raw_price = _prompt("Limit price (USDT)")
            try:
                price = validate_price(raw_price, filters, label="Limit price")
                break
            except ValueError as exc:
                _error(str(exc))

        time_in_force = _prompt_choice(
            "Time-in-force", ["GTC", "IOC", "FOK"], "GTC"
        )

    if order_type == "STOP_LIMIT":
        while True:
            raw_stop = _prompt("Stop (trigger) price (USDT)")
            try:
                stop_price = validate_price(raw_stop, filters, label="Stop price")
                break
            except ValueError as exc:
                _error(str(exc))

    # ── Confirm ────────────────────────────────────────────────────────────
    _println()
    _print_order_summary(
        symbol, side, order_type, quantity,
        price=price, stop_price=stop_price, time_in_force=time_in_force,
    )
    confirm = _prompt("Confirm order? (yes/no)", "yes").lower()
    if confirm not in {"yes", "y"}:
        _warn("Order cancelled.")
        return

    _place_and_display(
        manager, order_type, symbol, side, quantity,
        price=price, stop_price=stop_price, time_in_force=time_in_force,
    )


def _show_balance(client: BinanceFuturesClient) -> None:
    """Fetch and display USDT balance."""
    try:
        account = client.get_account()
    except (APIError, NetworkError) as exc:
        _error(f"Could not fetch balance: {exc}")
        return

    assets = account.get("assets", [])
    usdt = next((a for a in assets if a.get("asset") == "USDT"), None)

    _hr()
    _println("  ACCOUNT BALANCE", "bold")
    _hr()
    if usdt:
        _println(f"  Wallet Balance : {float(usdt.get('walletBalance', 0)):.4f} USDT")
        _println(f"  Unrealised PnL : {float(usdt.get('unrealizedProfit', 0)):.4f} USDT")
        _println(f"  Margin Balance : {float(usdt.get('marginBalance', 0)):.4f} USDT")
        _println(f"  Available      : {float(usdt.get('availableBalance', 0)):.4f} USDT")
    else:
        _warn("No USDT asset found in account.")
    _hr()


# ---------------------------------------------------------------------------
# Argument parser (direct mode)
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="primetrade",
        description=textwrap.dedent("""\
            PrimeTrade – Binance Futures Testnet CLI

            Place Market, Limit, or Stop-Limit orders via command line
            or an interactive guided menu.

            Environment variables required:
              BINANCE_API_KEY
              BINANCE_API_SECRET
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              # Market buy
              python cli.py --symbol BTCUSDT --side BUY --type MARKET --qty 0.001

              # Limit sell
              python cli.py --symbol BTCUSDT --side SELL --type LIMIT --qty 0.001 --price 70000

              # Stop-Limit buy
              python cli.py --symbol BTCUSDT --side BUY --type STOP_LIMIT \\
                            --qty 0.001 --stop-price 65000 --price 64900

              # Interactive mode
              python cli.py
        """),
    )

    parser.add_argument("--symbol",     "-s",  help="Trading symbol (e.g. BTCUSDT)")
    parser.add_argument(
        "--side",       "-d",
        choices=["BUY", "SELL"],
        type=str.upper,
        help="Order side",
    )
    parser.add_argument(
        "--type",       "-t",
        dest="order_type",
        choices=["MARKET", "LIMIT", "STOP_LIMIT"],
        type=str.upper,
        help="Order type",
    )
    parser.add_argument("--qty",        "-q",  help="Order quantity (base asset)")
    parser.add_argument("--price",      "-p",  help="Limit price (required for LIMIT / STOP_LIMIT)")
    parser.add_argument("--stop-price", "-sp", dest="stop_price", help="Stop/trigger price (required for STOP_LIMIT)")
    parser.add_argument(
        "--tif",
        default="GTC",
        choices=["GTC", "IOC", "FOK"],
        type=str.upper,
        help="Time-in-force for LIMIT orders (default: GTC)",
    )
    parser.add_argument(
        "--log-dir",
        default=os.getenv("LOG_DIR", "logs"),
        help="Directory for log files (default: ./logs)",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("BINANCE_BASE_URL", "https://testnet.binancefuture.com"),
        help="Binance Futures base URL",
    )
    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()

    # ── Logging ────────────────────────────────────────────────────────────
    # Resolve log dir relative to cli.py's location so it works from any cwd
    log_dir = Path(__file__).parent / args.log_dir
    setup_logging(log_dir=log_dir)

    # ── Credentials ────────────────────────────────────────────────────────
    api_key, api_secret, base_url = _load_credentials()
    if args.base_url:
        base_url = args.base_url

    # ── Determine mode ─────────────────────────────────────────────────────
    direct_mode = bool(args.symbol and args.side and args.order_type and args.qty)

    if not direct_mode:
        # ── Interactive ────────────────────────────────────────────────────
        # Still need exchange info for validation
        client    = BinanceFuturesClient(api_key, api_secret, base_url)
        _println("  Connecting to Binance Futures Testnet …", "cyan")
        try:
            exchange_info = client.get_exchange_info()
        except (APIError, NetworkError) as exc:
            _error(f"Failed to connect: {exc}")
            logger.exception("Startup: failed to fetch exchange info")
            sys.exit(1)

        manager = OrderManager(client, exchange_info)
        interactive_mode(client, manager, exchange_info)
        return

    # ── Direct mode ────────────────────────────────────────────────────────
    _println(BANNER, "cyan")

    client, manager, exchange_info = _build_client_and_manager(
        api_key, api_secret, base_url, args.symbol
    )

    # Validate symbol
    try:
        symbol = validate_symbol(args.symbol, exchange_info)
    except ValueError as exc:
        _error(str(exc))
        sys.exit(1)

    order_type = args.order_type

    # Validate LIMIT / STOP_LIMIT requirements
    if order_type in {"LIMIT", "STOP_LIMIT"} and not args.price:
        _error(f"--price is required for {order_type} orders.")
        sys.exit(1)
    if order_type == "STOP_LIMIT" and not args.stop_price:
        _error("--stop-price is required for STOP_LIMIT orders.")
        sys.exit(1)

    filters  = get_symbol_filters(symbol, exchange_info)

    # Validate quantity
    try:
        quantity = validate_quantity(args.qty, filters)
    except ValueError as exc:
        _error(f"Invalid quantity: {exc}")
        sys.exit(1)

    # Validate prices
    price      = None
    stop_price = None

    if args.price:
        try:
            price = validate_price(args.price, filters, label="Limit price")
        except ValueError as exc:
            _error(f"Invalid price: {exc}")
            sys.exit(1)

    if args.stop_price:
        try:
            stop_price = validate_price(args.stop_price, filters, label="Stop price")
        except ValueError as exc:
            _error(f"Invalid stop price: {exc}")
            sys.exit(1)

    # Print summary and place
    _print_order_summary(
        symbol, args.side, order_type, quantity,
        price=price, stop_price=stop_price,
        time_in_force=args.tif if order_type != "MARKET" else None,
    )

    _place_and_display(
        manager, order_type, symbol, args.side, quantity,
        price=price, stop_price=stop_price, time_in_force=args.tif,
    )


if __name__ == "__main__":
    main()
