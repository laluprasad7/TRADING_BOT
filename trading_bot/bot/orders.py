"""
orders.py – Order placement logic for PrimeTrade.

Provides :class:`OrderManager` which wraps the low-level
:class:`~bot.client.BinanceFuturesClient` and exposes clean, well-logged
methods for placing Market, Limit, and Stop-Limit orders.
"""

from __future__ import annotations

import logging
from typing import Any

from .client import BinanceFuturesClient, APIError, NetworkError
from .validators import (
    validate_quantity,
    validate_price,
    validate_time_in_force,
    get_symbol_filters,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_float(value: str | float | None, decimals: int = 8) -> str:
    """Format a numeric string for display, stripping trailing zeros."""
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.{decimals}f}".rstrip("0").rstrip(".")
    except (ValueError, TypeError):
        return str(value)


# ---------------------------------------------------------------------------
# OrderManager
# ---------------------------------------------------------------------------

class OrderManager:
    """High-level order placement API.

    Args:
        client:        Authenticated :class:`BinanceFuturesClient` instance.
        exchange_info: Cached exchange info dict (used for filter validation).
    """

    def __init__(
        self,
        client: BinanceFuturesClient,
        exchange_info: dict,
    ) -> None:
        self._client        = client
        self._exchange_info = exchange_info

    # ── Internal helper ───────────────────────────────────────────────────

    def _get_filters(self, symbol: str) -> list[dict]:
        return get_symbol_filters(symbol, self._exchange_info)

    # ── Order placement ───────────────────────────────────────────────────

    def place_market(
        self,
        symbol: str,
        side: str,
        quantity: str | float,
    ) -> dict:
        """Place a MARKET order.

        Args:
            symbol:   Trading symbol (e.g. ``BTCUSDT``).
            side:     ``BUY`` or ``SELL``.
            quantity: Order quantity (base asset).

        Returns:
            Binance order response dictionary.

        Raises:
            ValueError:    Validation failed.
            APIError:      Binance rejected the order.
            NetworkError:  HTTP failure.
        """
        filters = self._get_filters(symbol)
        qty     = validate_quantity(quantity, filters)

        params: dict[str, Any] = {
            "symbol":   symbol,
            "side":     side,
            "type":     "MARKET",
            "quantity": qty,
        }

        logger.info(
            "Placing MARKET order",
            extra={"symbol": symbol, "side": side, "quantity": qty},
        )

        response = self._client.place_order(**params)

        logger.info(
            "MARKET order placed successfully",
            extra={
                "orderId":     response.get("orderId"),
                "status":      response.get("status"),
                "executedQty": response.get("executedQty"),
                "avgPrice":    response.get("avgPrice"),
            },
        )
        return response

    def place_limit(
        self,
        symbol: str,
        side: str,
        quantity: str | float,
        price: str | float,
        time_in_force: str = "GTC",
    ) -> dict:
        """Place a LIMIT order.

        Args:
            symbol:        Trading symbol.
            side:          ``BUY`` or ``SELL``.
            quantity:      Order quantity (base asset).
            price:         Limit price.
            time_in_force: GTC / IOC / FOK (default GTC).

        Returns:
            Binance order response dictionary.

        Raises:
            ValueError:    Validation failed.
            APIError:      Binance rejected the order.
            NetworkError:  HTTP failure.
        """
        filters = self._get_filters(symbol)
        qty     = validate_quantity(quantity, filters)
        prc     = validate_price(price, filters, label="Limit price")
        tif     = validate_time_in_force(time_in_force)

        params: dict[str, Any] = {
            "symbol":      symbol,
            "side":        side,
            "type":        "LIMIT",
            "quantity":    qty,
            "price":       prc,
            "timeInForce": tif,
        }

        logger.info(
            "Placing LIMIT order",
            extra={
                "symbol":        symbol,
                "side":          side,
                "quantity":      qty,
                "price":         prc,
                "timeInForce":   tif,
            },
        )

        response = self._client.place_order(**params)

        logger.info(
            "LIMIT order placed successfully",
            extra={
                "orderId":     response.get("orderId"),
                "status":      response.get("status"),
                "executedQty": response.get("executedQty"),
                "price":       response.get("price"),
            },
        )
        return response

    def place_stop_limit(
        self,
        symbol: str,
        side: str,
        quantity: str | float,
        stop_price: str | float,
        price: str | float,
        time_in_force: str = "GTC",
    ) -> dict:
        """Place a STOP / STOP_MARKET order.  (Bonus order type)

        On Binance Futures the ``STOP`` type requires both a *stopPrice*
        (trigger) and a *price* (limit price after trigger).

        Args:
            symbol:        Trading symbol.
            side:          ``BUY`` or ``SELL``.
            quantity:      Order quantity (base asset).
            stop_price:    Trigger price.
            price:         Limit price (executed after trigger).
            time_in_force: GTC / IOC / FOK (default GTC).

        Returns:
            Binance order response dictionary.

        Raises:
            ValueError:    Validation failed.
            APIError:      Binance rejected the order.
            NetworkError:  HTTP failure.
        """
        filters = self._get_filters(symbol)
        qty     = validate_quantity(quantity, filters)
        sp      = validate_price(stop_price, filters, label="Stop price")
        prc     = validate_price(price, filters, label="Limit price")
        tif     = validate_time_in_force(time_in_force)

        params: dict[str, Any] = {
            "symbol":      symbol,
            "side":        side,
            "type":        "STOP",
            "quantity":    qty,
            "stopPrice":   sp,
            "price":       prc,
            "timeInForce": tif,
        }

        logger.info(
            "Placing STOP_LIMIT order",
            extra={
                "symbol":        symbol,
                "side":          side,
                "quantity":      qty,
                "stopPrice":     sp,
                "price":         prc,
                "timeInForce":   tif,
            },
        )

        response = self._client.place_order(**params)

        logger.info(
            "STOP_LIMIT order placed successfully",
            extra={
                "orderId":     response.get("orderId"),
                "status":      response.get("status"),
                "executedQty": response.get("executedQty"),
                "stopPrice":   response.get("stopPrice"),
                "price":       response.get("price"),
            },
        )
        return response

    # ── Response formatting ───────────────────────────────────────────────

    @staticmethod
    def format_order_response(response: dict) -> str:
        """Return a human-readable summary of an order response.

        Args:
            response: Binance order response dictionary.

        Returns:
            Multi-line string suitable for CLI output.
        """
        order_id    = response.get("orderId", "N/A")
        client_id   = response.get("clientOrderId", "N/A")
        symbol      = response.get("symbol", "N/A")
        side        = response.get("side", "N/A")
        order_type  = response.get("type", response.get("origType", "N/A"))
        status      = response.get("status", "N/A")
        exec_qty    = _fmt_float(response.get("executedQty"), 6)
        orig_qty    = _fmt_float(response.get("origQty"), 6)
        avg_price   = _fmt_float(response.get("avgPrice"), 2)
        price       = _fmt_float(response.get("price"), 2)
        stop_price  = _fmt_float(response.get("stopPrice"), 2)
        tif         = response.get("timeInForce", "N/A")
        update_time = response.get("updateTime", "N/A")

        lines = [
            "─" * 52,
            f"  Order ID      : {order_id}",
            f"  Client ID     : {client_id}",
            f"  Symbol        : {symbol}",
            f"  Side          : {side}",
            f"  Type          : {order_type}",
            f"  Status        : {status}",
            f"  Quantity      : {exec_qty} / {orig_qty}",
            f"  Avg Price     : {avg_price}",
        ]

        if order_type in {"LIMIT", "STOP", "STOP_LIMIT"}:
            lines.append(f"  Limit Price   : {price}")
        if order_type in {"STOP", "STOP_MARKET", "STOP_LIMIT"}:
            lines.append(f"  Stop Price    : {stop_price}")
        if tif != "N/A":
            lines.append(f"  Time-in-Force : {tif}")

        lines += [
            f"  Updated At    : {update_time}",
            "─" * 52,
        ]

        return "\n".join(lines)
