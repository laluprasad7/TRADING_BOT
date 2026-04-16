"""
client.py – Low-level Binance Futures REST client.

Handles:
  - HMAC-SHA256 request signing
  - Timestamp injection
  - Retryable HTTP requests with back-off
  - Structured request / response logging
  - APIError exception propagation
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
import urllib.parse
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class APIError(Exception):
    """Raised when Binance returns a non-2xx response or an error payload."""

    def __init__(self, status_code: int, code: int, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(f"[HTTP {status_code}] Binance error {code}: {message}")


class NetworkError(Exception):
    """Raised on connection / timeout failures."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

_DEFAULT_BASE_URL = "https://testnet.binancefuture.com"
_DEFAULT_TIMEOUT  = 10          # seconds
_MAX_RETRIES      = 3
_BACKOFF_FACTOR   = 0.4


class BinanceFuturesClient:
    """Thin wrapper around the Binance USDT-M Futures REST API.

    Args:
        api_key:    Binance API key.
        api_secret: Binance API secret (used for HMAC signing).
        base_url:   Override base URL (defaults to testnet).
        timeout:    HTTP request timeout in seconds.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        self._api_key    = api_key
        self._api_secret = api_secret.encode()          # bytes for hmac
        self._base_url   = base_url.rstrip("/")
        self._timeout    = timeout
        self._session    = self._build_session()

    # ── Private helpers ───────────────────────────────────────────────────

    @staticmethod
    def _build_session() -> requests.Session:
        """Build a requests Session with retry logic."""
        session = requests.Session()
        retry = Retry(
            total=_MAX_RETRIES,
            backoff_factor=_BACKOFF_FACTOR,
            status_forcelist={429, 500, 502, 503, 504},
            allowed_methods={"GET", "POST", "DELETE"},
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _sign(self, query_string: str) -> str:
        """Return the HMAC-SHA256 signature for *query_string*."""
        return hmac.new(
            self._api_secret,
            query_string.encode(),
            hashlib.sha256,
        ).hexdigest()

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        signed: bool = True,
    ) -> Any:
        """Make a signed (or unsigned) request and return parsed JSON.

        Args:
            method:  HTTP verb (GET / POST / DELETE).
            path:    API path, e.g. ``/fapi/v1/order``.
            params:  Query / body parameters.
            signed:  If True, injects timestamp + signature.

        Returns:
            Parsed JSON response.

        Raises:
            APIError:    Binance returned an error payload.
            NetworkError: Connection / timeout failure.
        """
        params = dict(params or {})

        if signed:
            params["timestamp"] = int(time.time() * 1000)
            query_string = urllib.parse.urlencode(params)
            params["signature"] = self._sign(query_string)

        url = f"{self._base_url}{path}"
        headers = {"X-MBX-APIKEY": self._api_key}

        logger.debug(
            "API request",
            extra={
                "method": method,
                "url": url,
                "params": {k: v for k, v in params.items() if k != "signature"},
            },
        )

        try:
            if method.upper() in {"GET", "DELETE"}:
                resp = self._session.request(
                    method, url, params=params, headers=headers, timeout=self._timeout
                )
            else:  # POST / PUT
                resp = self._session.request(
                    method, url, data=params, headers=headers, timeout=self._timeout
                )
        except requests.exceptions.Timeout as exc:
            logger.error("Request timed out: %s %s", method, url)
            raise NetworkError(f"Request timed out: {exc}") from exc
        except requests.exceptions.ConnectionError as exc:
            logger.error("Connection error: %s %s", method, url)
            raise NetworkError(f"Connection error: {exc}") from exc

        # Parse response
        try:
            data = resp.json()
        except ValueError:
            data = resp.text

        logger.debug(
            "API response",
            extra={
                "status_code": resp.status_code,
                "body": data,
            },
        )

        # Error handling
        if not resp.ok or (isinstance(data, dict) and "code" in data and data["code"] < 0):
            if isinstance(data, dict):
                raise APIError(
                    status_code=resp.status_code,
                    code=data.get("code", -1),
                    message=data.get("msg", "Unknown error"),
                )
            raise APIError(
                status_code=resp.status_code,
                code=-1,
                message=str(data),
            )

        return data

    # ── Public API methods ────────────────────────────────────────────────

    def get_exchange_info(self, symbol: str | None = None) -> dict:
        """Fetch exchange info (symbols, filters).

        Args:
            symbol: If provided, fetch info for this symbol only.

        Returns:
            Exchange info dictionary.
        """
        params: dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol.upper()
        return self._request("GET", "/fapi/v1/exchangeInfo", params=params, signed=False)

    def get_account(self) -> dict:
        """Return account details including balances and positions."""
        return self._request("GET", "/fapi/v2/account")

    def place_order(self, **kwargs: Any) -> dict:
        """Submit a new order.

        All keyword arguments are passed directly as order parameters, e.g.::

            client.place_order(
                symbol="BTCUSDT",
                side="BUY",
                type="MARKET",
                quantity="0.001",
            )

        Returns:
            Order response dictionary from Binance.
        """
        return self._request("POST", "/fapi/v1/order", params=kwargs)

    def get_order(self, symbol: str, order_id: int) -> dict:
        """Query order status.

        Args:
            symbol:   Trading symbol.
            order_id: Binance order ID.

        Returns:
            Order detail dictionary.
        """
        return self._request(
            "GET",
            "/fapi/v1/order",
            params={"symbol": symbol.upper(), "orderId": order_id},
        )
