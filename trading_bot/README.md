# Binance Futures Testnet Trading Bot

A clean, well-structured Python CLI for placing orders on
**Binance USDT-M Futures Testnet** with full logging and robust error handling.

---

## Features

| Feature | Details |
|---|---|
| Order types | Market, Limit, Stop-Limit (bonus) |
| Sides | BUY / SELL |
| Modes | Direct CLI (`--symbol … --side … --type …`) and interactive guided menu |
| Validation | Exchange-info–aware (lot size, tick size, min/max qty/price) |
| Logging | Rotating JSON log file (DEBUG) + colourised console (INFO) |
| Error handling | Validation errors, Binance API errors, network failures |

---

## Project Structure

```
trading_bot/
  bot/
    __init__.py          # Package marker
    client.py            # BinanceFuturesClient – HMAC-signed REST calls
    orders.py            # OrderManager – place_market / place_limit / place_stop_limit
    validators.py        # Input validation helpers
    logging_config.py    # Rotating file + console handler setup
  cli.py                 # CLI entry point
  logs/                  # Created automatically at runtime
  README.md
  requirements.txt
```

---

## Setup

### 1. Register on Binance Futures Testnet

1. Go to <https://testnet.binancefuture.com> and log in with your GitHub account.
2. Under **API Management** (top-right menu), generate a new API key.
3. Copy the **API Key** and **Secret Key** – you will need them below.

### 2. Clone / unzip and install dependencies

```bash
cd trading_bot
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure credentials

Create a `.env` file in the `trading_bot/` directory:

```ini
BINANCE_API_KEY=your_testnet_api_key_here
BINANCE_API_SECRET=your_testnet_api_secret_here

# Optional overrides
# BINANCE_BASE_URL=https://testnet.binancefuture.com
# LOG_DIR=logs
```

> **Never commit your `.env` file.** It is already listed in `.gitignore`.

---

## How to Run

All commands are run from the `trading_bot/` directory with the virtual environment active.

### Direct Mode (single command)

```bash
# Market BUY
python cli.py --symbol BTCUSDT --side BUY --type MARKET --qty 0.001

# Limit SELL
python cli.py --symbol BTCUSDT --side SELL --type LIMIT --qty 0.001 --price 70000

# Stop-Limit BUY  (bonus order type)
python cli.py --symbol BTCUSDT --side BUY --type STOP_LIMIT \
              --qty 0.001 --stop-price 65000 --price 64900

# Limit with custom time-in-force
python cli.py --symbol ETHUSDT --side BUY --type LIMIT \
              --qty 0.01 --price 2000 --tif IOC
```

### Interactive Mode (guided menu)

```bash
python cli.py
```

The app will display a menu: place orders, view balance, or exit.
Each field is prompted with live validation — errors are flagged immediately
and you can re-enter without restarting.

### Help

```bash
python cli.py --help
```

---

## Logging

Log files are written to `trading_bot/logs/trading_bot.log`.

- **File**: DEBUG level, JSON-structured, rotating (10 MB × 5 backups).
- **Console**: INFO level, human-readable with ANSI colours.

### Sample log lines (formatted for readability)

```json
{"ts": "2025-01-01T12:00:00+00:00", "level": "INFO",  "logger": "primetrade.cli",     "message": "Logging initialised"}
{"ts": "2025-01-01T12:00:01+00:00", "level": "DEBUG", "logger": "bot.client",         "message": "API request", "method": "GET",  "url": "https://testnet.binancefuture.com/fapi/v1/exchangeInfo"}
{"ts": "2025-01-01T12:00:01+00:00", "level": "DEBUG", "logger": "bot.client",         "message": "API response", "status_code": 200}
{"ts": "2025-01-01T12:00:02+00:00", "level": "INFO",  "logger": "bot.orders",         "message": "Placing MARKET order",  "symbol": "BTCUSDT", "side": "BUY", "quantity": "0.001"}
{"ts": "2025-01-01T12:00:02+00:00", "level": "DEBUG", "logger": "bot.client",         "message": "API request", "method": "POST", "url": "https://testnet.binancefuture.com/fapi/v1/order"}
{"ts": "2025-01-01T12:00:03+00:00", "level": "INFO",  "logger": "bot.orders",         "message": "MARKET order placed successfully", "orderId": 123456, "status": "FILLED"}
```

---

## Assumptions & Notes

1. **Testnet only** – The default base URL is `https://testnet.binancefuture.com`. To use mainnet, set `BINANCE_BASE_URL` in `.env` (not recommended for automated trading without thorough testing).
2. **USDT-M Futures** – All orders target the USDT-margined perpetual contract market.
3. **Quantity precision** – The CLI auto-rounds quantities and prices to the exchange's `stepSize` / `tickSize` to prevent order rejection.
4. **Stop-Limit type** – Uses Binance's `STOP` order type (not `STOP_MARKET`), which requires both a `stopPrice` (trigger) and a `price` (limit price after trigger).
5. **python-binance not used** – Direct `requests`-based REST calls are used for full control and transparency over request signing and error handling.
6. **No position management** – This bot places orders only; it does not track positions, PnL, or implement any trading strategy.

---

## Requirements

```
requests>=2.31.0
urllib3>=2.0.0
python-dotenv>=1.0.0
```

Python 3.9+ recommended.
