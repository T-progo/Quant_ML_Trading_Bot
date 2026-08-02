# Crypto Trading Bot (Binance Testnet)

A strategy-based trading bot using Moving Averages, RSI, MACD, and Bollinger
Bands. Includes a backtester, a paper trading mode (fake money, live data),
live testnet execution (real orders, fake funds), and a Flask API to check
status remotely.

**No real money is ever used unless you manually change `USE_TESTNET = False`
in `config/settings.py` — do not do that until you've thoroughly tested this.**

---

## 1. Prerequisites

- Python 3.10+ installed
- VS Code (with the Python extension)
- A free Binance Testnet account: https://testnet.binance.vision/ (log in with GitHub, then generate an API key + secret)

> **Note:** this project uses `pandas-ta-classic` (not the original `pandas-ta`,
> which was discontinued on PyPI and now requires Python 3.12+). If you ever
> see `pandas_ta` referenced elsewhere online, use `pandas_ta_classic` instead
> — the function calls are identical.

## 2. Setup

Open the project folder in VS Code, then open a terminal (`Terminal > New Terminal`) and run:

```bash
# 1. Create a virtual environment
python -m venv venv

# 2. Activate it
# On Windows (PowerShell):
venv\Scripts\Activate.ps1
# On Mac/Linux:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

If PowerShell blocks the activation script, run this once as admin:
`Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

## 3. Configure your API keys

```bash
# Copy the example env file
copy .env.example .env      # Windows
cp .env.example .env        # Mac/Linux
```

Open `.env` and paste in your Binance **testnet** API key and secret (from
https://testnet.binance.vision/). You can leave everything else as default.

## 4. Project structure

```
crypto_trading_bot/
├── config/settings.py       # all settings: symbol, strategy params, risk %
├── data/fetcher.py          # fetches OHLCV candle data via ccxt
├── strategies/indicators.py # MA/RSI/MACD/Bollinger + signal logic
├── backtest/backtester.py   # simulates strategy on historical data
├── execution/
│   ├── paper_trader.py      # simulated trades on live data (fake money)
│   └── testnet_trader.py    # REAL orders on Binance testnet (fake funds)
├── api/app.py                # Flask API to check bot status remotely
├── run_backtest.py           # CLI entry point for backtesting
├── requirements.txt
├── .env.example
└── README.md
```

## 5. Running each mode

### A) Backtest on historical data (start here — no API keys needed for this)

```bash
python run_backtest.py --symbol BTC/USDT --timeframe 15m --start 2025-01-01 --end 2025-06-01
```

This prints a report: final balance, win rate, number of trades. Tweak
strategy parameters in `config/settings.py` and re-run to compare.

### B) Paper trading (fake money, live prices)

```bash
python execution/paper_trader.py
```

Runs forever, checking for signals every 60 seconds (configurable via
`POLL_INTERVAL_SECONDS` in settings). State is saved to
`logs/paper_trader_state.json` so you can stop/restart without losing your
balance or trade history. Press `Ctrl+C` to stop.

### C) Live testnet trading (real orders, but on Binance's fake-money testnet)

Requires your API keys to be set in `.env`.

```bash
python execution/testnet_trader.py
```

This places actual market orders against Binance's testnet — good for
validating order execution, slippage, and fees before ever considering real
funds.

### D) Flask API (check bot status from a browser or your phone)

```bash
python api/app.py
```

Then visit in a browser (or from Postman / your Flutter app later):

- `http://localhost:5000/health` — check the API is running
- `http://localhost:5000/signal` — current price + BUY/SELL/HOLD signal
- `http://localhost:5000/paper/status` — paper trading balance & trade log
- `http://localhost:5000/paper/tick` — (POST) manually trigger one paper-trading check
- `http://localhost:5000/backtest?symbol=BTC/USDT&timeframe=15m&start=2025-01-01` — run a backtest via API

## 6. Tuning the strategy

Edit `config/settings.py`:

- `FAST_MA` / `SLOW_MA` — moving average crossover lengths
- `RSI_PERIOD`, `RSI_OVERBOUGHT`, `RSI_OVERSOLD`
- `MACD_FAST`, `MACD_SLOW`, `MACD_SIGNAL`
- `BB_PERIOD`, `BB_STD` — Bollinger Band settings
- `STOP_LOSS_PCT`, `TAKE_PROFIT_PCT` — risk management
- `TRADE_AMOUNT_USDT` — position size per trade

After any change, re-run `run_backtest.py` to see the impact before running
paper or testnet trading.

## 6b. Trying different strategies

`run_backtest.py` and `run_walkforward.py` both take a `--strategy` flag so
you can compare approaches on the same data without editing code:

```bash
python run_backtest.py --strategy legacy --start 2023-01-01 --end 2023-10-01
python run_backtest.py --strategy breakout --start 2023-01-01 --end 2023-10-01
python run_backtest.py --strategy volatility --start 2023-01-01 --end 2023-10-01
python run_backtest.py --strategy supertrend --start 2023-01-01 --end 2023-10-01
python run_backtest.py --strategy ml --start 2023-01-01 --end 2023-10-01 --ml-train-months 12

python run_walkforward.py --strategy breakout --symbol BTC/USDT --timeframe 1h --start 2021-01-01 --end 2025-06-01
```

Strategies available:

| `--strategy` | Idea | File |
|---|---|---|
| `legacy` | MA-cross + MACD + RSI trend mode, RSI/Bollinger mean-reversion in ranging markets | `strategies/indicators.py` |
| `breakout` | Donchian-channel N-bar breakout, confirmed by volume + ADX | `strategies/breakout.py` |
| `volatility` | Bollinger Band squeeze, then trade the direction it breaks out of | `strategies/volatility_squeeze.py` |
| `supertrend` | Single ATR-based Supertrend indicator, trades on direction flips | `strategies/supertrend.py` |
| `ml` | Gradient-boosted classifier trained on engineered features (returns, RSI, MACD, ADX, ATR, volume z-score) to predict the next few bars' direction | `strategies/ml_classifier.py` |

All of these are **long-only** — this is a spot account, and none of them
open a short position. A bearish signal only closes an existing long early;
it never opens a new position.

The `ml` strategy retrains fresh on the trailing `--ml-train-months` of data
before every backtest/walk-forward window, and never trains on data from the
window it's then tested on — that avoids lookahead bias, at the cost of
retraining being slower than the rule-based strategies.

### Pairs / stat-arb (research only)

`strategies/pairs_stat_arb.py` trades the price ratio between two assets
(e.g. BTC vs ETH) instead of either one outright. **This one requires
shorting one leg while going long the other, which a spot account cannot
do** — it's not wired into `paper_trader.py` or `testnet_trader.py`, and it
has its own runner:

```bash
python run_pairs_backtest.py --symbol1 BTC/USDT --symbol2 ETH/USDT --timeframe 1h --start 2023-01-01 --end 2023-10-01
```

Treat its output as research: what the strategy *would* have earned with a
margin/futures account able to hold both legs, not a plan you can run as-is.

## 7. Recommended workflow

1. **Backtest** extensively across different date ranges and timeframes until
   the strategy looks solid (win rate, return, and drawdown you're comfortable with).
2. **Paper trade** for at least a week to confirm it behaves the same on live
   data as it did in backtests.
3. **Testnet trade** to validate real order execution mechanics.
4. Only after all three, consider (carefully, and at your own risk) real funds
   — and even then, start with a very small `TRADE_AMOUNT_USDT`.

## 8. Next steps (not included yet)

- Forex support via OANDA's practice API (same strategy code, new data adapter)
- Flutter mobile dashboard consuming the Flask API endpoints above
- Persistent database (currently paper trading state is a local JSON file)

---

**Disclaimer:** This is an educational project. Trading involves risk of loss.
Nothing here is financial advice. Test thoroughly before ever using real funds.
