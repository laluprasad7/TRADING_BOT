"""
validators.py – Input validation helpers for PrimeTrade.

All validators raise :class:`ValueError` with a human-readable message on
failure, so callers can catch them uniformly.
"""

from __future__ import annotations

import math
import re
from decimal import Decimal, ROUND_DOWN
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_SIDES        = {"BUY", "SELL"}
VALID_ORDER_TYPES  = {"MARKET", "LIMIT", "STOP_MARKET", "STOP_LIMIT"}
VALID_TIF          = {"GTC", "IOC", "FOK", "GTX"}    # time-in-force options


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_filter(filters: list[dict], filter_type: str) -> dict[str, Any]:
    """Return the filter dict matching *filter_type* from exchange info, or {}."""
    for f in filters:
        if f.get("filterType") == filter_type:
            return f
    return {}


def _round_to_step(value: Decimal, step: Decimal) -> Decimal:
    """Round *value* DOWN to the nearest multiple of *step*."""
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


# ---------------------------------------------------------------------------
# Public validators
# ---------------------------------------------------------------------------

def validate_symbol(symbol: str, exchange_info: dict) -> str:
    """Ensure *symbol* is a valid, currently trading symbol.

    Args:
        symbol:        Raw input string.
        exchange_info: Response from ``GET /fapi/v1/exchangeInfo``.

    Returns:
        Upper-cased symbol string.

    Raises:
        ValueError: Symbol is not found or not in TRADING status.
    """
    symbol = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{2,20}", symbol):
        raise ValueError(
            f"'{symbol}' is not a valid symbol format. "
            "Expected something like BTCUSDT."
        )

    trading_symbols = {
        s["symbol"]
        for s in exchange_info.get("symbols", [])
        if s.get("status") == "TRADING"
    }
    if symbol not in trading_symbols:
        close = [s for s in trading_symbols if symbol[:3] in s][:5]
        hint = f"  Did you mean one of: {', '.join(close)}?" if close else ""
        raise ValueError(
            f"Symbol '{symbol}' is not currently trading on this exchange.{hint}"
        )
    return symbol


def validate_side(side: str) -> str:
    """Validate order side (BUY/SELL).

    Returns:
        Upper-cased side.

    Raises:
        ValueError: Side is not recognised.
    """
    side = side.strip().upper()
    if side not in VALID_SIDES:
        raise ValueError(
            f"Side '{side}' is invalid. Must be one of: {', '.join(sorted(VALID_SIDES))}."
        )
    return side


def validate_order_type(order_type: str) -> str:
    """Validate order type.

    Returns:
        Upper-cased order type.

    Raises:
        ValueError: Order type is not supported.
    """
    order_type = order_type.strip().upper()
    if order_type not in VALID_ORDER_TYPES:
        raise ValueError(
            f"Order type '{order_type}' is not supported. "
            f"Choose from: {', '.join(sorted(VALID_ORDER_TYPES))}."
        )
    return order_type


def validate_quantity(
    quantity: str | float,
    symbol_filters: list[dict],
) -> str:
    """Validate and normalise order quantity against LOT_SIZE filter.

    Args:
        quantity:       Raw quantity input.
        symbol_filters: ``filters`` list from exchange info for the symbol.

    Returns:
        Quantity as a string rounded to the allowed step size.

    Raises:
        ValueError: Quantity is non-positive, below min, above max, or
                    not a valid number.
    """
    try:
        qty = Decimal(str(quantity))
    except Exception:
        raise ValueError(f"Quantity '{quantity}' is not a valid number.")

    if qty <= 0:
        raise ValueError("Quantity must be a positive number.")

    lot = _extract_filter(symbol_filters, "LOT_SIZE")
    if lot:
        min_qty  = Decimal(lot.get("minQty",  "0"))
        max_qty  = Decimal(lot.get("maxQty",  "999999999"))
        step     = Decimal(lot.get("stepSize", "0"))

        if qty < min_qty:
            raise ValueError(
                f"Quantity {qty} is below the minimum allowed ({min_qty})."
            )
        if qty > max_qty:
            raise ValueError(
                f"Quantity {qty} exceeds the maximum allowed ({max_qty})."
            )
        if step > 0:
            qty = _round_to_step(qty, step)
            if qty <= 0:
                raise ValueError(
                    f"Quantity rounds to zero with step size {step}. "
                    f"Please enter a larger value (min: {min_qty})."
                )

    return str(qty.normalize())


def validate_price(
    price: str | float,
    symbol_filters: list[dict],
    label: str = "Price",
) -> str:
    """Validate and normalise a price value against PRICE_FILTER.

    Args:
        price:          Raw price input.
        symbol_filters: ``filters`` list from exchange info for the symbol.
        label:          Human-readable label for error messages (default "Price").

    Returns:
        Price as a string rounded to the allowed tick size.

    Raises:
        ValueError: Price is non-positive or not a valid number.
    """
    try:
        p = Decimal(str(price))
    except Exception:
        raise ValueError(f"{label} '{price}' is not a valid number.")

    if p <= 0:
        raise ValueError(f"{label} must be a positive number.")

    pf = _extract_filter(symbol_filters, "PRICE_FILTER")
    if pf:
        min_price = Decimal(pf.get("minPrice", "0"))
        max_price = Decimal(pf.get("maxPrice", "9999999"))
        tick      = Decimal(pf.get("tickSize", "0"))

        if min_price > 0 and p < min_price:
            raise ValueError(
                f"{label} {p} is below the minimum allowed ({min_price})."
            )
        if max_price > 0 and p > max_price:
            raise ValueError(
                f"{label} {p} exceeds the maximum allowed ({max_price})."
            )
        if tick > 0:
            p = _round_to_step(p, tick)

    return str(p.normalize())


def validate_time_in_force(tif: str) -> str:
    """Validate time-in-force value.

    Returns:
        Upper-cased TIF.

    Raises:
        ValueError: TIF is not recognised.
    """
    tif = tif.strip().upper()
    if tif not in VALID_TIF:
        raise ValueError(
            f"Time-in-force '{tif}' is invalid. "
            f"Valid options: {', '.join(sorted(VALID_TIF))}."
        )
    return tif


def get_symbol_filters(symbol: str, exchange_info: dict) -> list[dict]:
    """Extract the filters list for *symbol* from exchange info.

    Returns:
        Filters list, or empty list if symbol not found.
    """
    symbol = symbol.upper()
    for s in exchange_info.get("symbols", []):
        if s["symbol"] == symbol:
            return s.get("filters", [])
    return []


def get_symbol_precision(symbol: str, exchange_info: dict) -> tuple[int, int]:
    """Return (price_precision, quantity_precision) for *symbol*.

    Returns:
        Tuple of (price_precision, quantity_precision).
    """
    symbol = symbol.upper()
    for s in exchange_info.get("symbols", []):
        if s["symbol"] == symbol:
            return s.get("pricePrecision", 8), s.get("quantityPrecision", 8)
    return 8, 8
