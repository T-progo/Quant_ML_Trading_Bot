# Quant Trading Bot

A multi-strategy cryptocurrency trading bot for Binance, built around
rigorous backtesting rather than guesswork. Includes trend-following,
mean-reversion, breakout, volatility, SuperTrend, and machine-learning
strategies, walk-forward validation, and risk-adjusted performance reporting
(Sharpe, Calmar) alongside paper trading and testnet/live execution.

**No real money is ever used unless you deliberately clear three separate
safety checks — see [Going Live](#8-going-live) below. Don't do that until
you've thoroughly tested this.**

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
https://testnet.binance.vision/). Leave everything else as default for now.

## 4. Project structure

```
quant-trading-bot/
├── config/settings.py         # all tunable parameters (strategy, risk, fees)
├── data/fetcher.py            # OHLCV candle data via ccxt (Binance)
├── strategies/
│   ├── indicators.py          # legacy: MA/RSI/MACD trend + mean-reversion mode
│   ├── breakout.py            # Donchian-channel breakout
│   ├── volatility_squeeze.py  # Bollinger Band squeeze breakout
│   ├── supertrend.py          # ATR-based Supertrend
│   ├── ml_classifier.py       # gradient-boosted classifier, scheduled retraining
│   ├── pairs_stat_arb.py      # BTC/ETH pairs trading (research only, spot-incompatible)
│   └── registry.py            # strategy lookup by name
├── backtest/backtester.py     # fee-aware backtest engine + buy-and-hold benchmark
├── execution/
│   ├── paper_trader.py        # simulated trades on live data (fake money)
│   ├── testnet_trader.py      # legacy strategy only, real orders on testnet
│   └── live_trader.py         # ALL strategies; testnet by default, real-account
│                               # trading gated behind 3 confirmations (see below)
├── api/app.py                 # Flask API to check bot status remotely
├── run_backtest.py            # single backtest CLI (any --strategy)
├── run_walkforward.py         # rolling-window validation (catches overfitting)
├── run_comparison.py          # compare across symbols/timeframes
├── run_risk_report.py         # Sharpe / Calmar / max drawdown vs buy-and-hold
├── run_pairs_backtest.py      # pairs/stat-arb backtest (research only)
├── check_trade.py             # on-demand "should I trade right now?" check
├── requirements.txt
├── .env.example
└── README.md
```

## 5. Running each mode

### A) Backtest on historical data (start here — no API keys needed)

```bash
python run_backtest.py --strategy legacy --symbol BTC/USDT --timeframe 1h --start 2024-01-01 --end 2025-06-01
```

Prints final balance, win rate, avg win/loss, fees paid, and a **buy-and-hold
comparison** so results are judged against a real alternative, not in isolation.

### B) Walk-forward validation (do this before trusting any single backtest)

```bash
python run_walkforward.py --strategy legacy --symbol BTC/USDT --timeframe 1h --start 2021-01-01 --end 2025-06-01 --window-months 3
```

Splits the range into sequential windows and backtests each separately, then
reports how many windows beat buy-and-hold and the average return per
window — a single good backtest can be luck; consistency across many windows
is a much stronger signal.

### C) Risk-adjusted report (Sharpe / Calmar / max drawdown)

```bash
python run_risk_report.py --strategy ml --symbol BTC/USDT --timeframe 1h --start 2021-01-01 --end 2025-06-01 --ml-train-months 12
```

Win rate and raw return don't tell you if the risk taken was worth it. This
computes the same risk-adjusted metrics professionals use to judge a
strategy against buy-and-hold, not just against zero.

### D) On-demand signal check (no trading)

```bash
python check_trade.py --symbol BTC/USDT --timeframe 1h
```

### E) Paper trading (fake money, live prices)

```bash
python execution/paper_trader.py
```

Runs forever, checking for signals every 60 seconds (`POLL_INTERVAL_SECONDS`
in settings). State persists to `logs/paper_trader_state.json`. `Ctrl+C` to stop.

### F) Live/testnet trader — all strategies

```bash
python -m execution.live_trader --strategy supertrend
python -m execution.live_trader --strategy ml --ml-train-months 12 --ml-retrain-days 30
```

Testnet by default. For the ML strategy, it trains on a trailing window of
real historical data and retrains on a schedule instead of going stale.

### G) Flask API (check bot status from a browser or your phone)

```bash
python api/app.py
```

- `http://localhost:5000/health`
- `http://localhost:5000/signal` — current price + BUY/SELL/HOLD + mode
- `http://localhost:5000/paper/status` — paper trading balance & trade log
- `http://localhost:5000/paper/tick` — (POST) manually trigger one check
- `http://localhost:5000/backtest?symbol=BTC/USDT&timeframe=15m&start=2025-01-01`

## 6. Tuning the strategy

Edit `config/settings.py` — key parameters:

- `FAST_MA` / `SLOW_MA` / `TREND_MA` — moving average lengths
- `RSI_PERIOD`, `RSI_OVERBOUGHT`, `RSI_OVERSOLD`
- `MACD_FAST`, `MACD_SLOW`, `MACD_SIGNAL`
- `BB_PERIOD`, `BB_STD` — Bollinger Bands
- `ADX_MIN_STRENGTH` — trend-strength filter (below this, switches to mean-reversion mode)
- `ATR_STOP_MULT`, `ATR_TRAIL_MULT` — volatility-scaled stop-loss/trailing distance
- `TRADING_FEE_PCT` — fee simulation in backtests
- `TRADE_AMOUNT_USDT` — position size per trade

Re-run `run_backtest.py` after any change before trusting it in paper/live mode.

## 6b. Trying different strategies

`run_backtest.py`, `run_walkforward.py`, `run_risk_report.py`, and
`execution/live_trader.py` all take a `--strategy` flag:

```bash
python run_backtest.py --strategy legacy --start 2023-01-01 --end 2023-10-01
python run_backtest.py --strategy breakout --start 2023-01-01 --end 2023-10-01
python run_backtest.py --strategy volatility --start 2023-01-01 --end 2023-10-01
python run_backtest.py --strategy supertrend --start 2023-01-01 --end 2023-10-01
python run_backtest.py --strategy ml --start 2023-01-01 --end 2023-10-01 --ml-train-months 12
```

| `--strategy` | Idea | File |
|---|---|---|
| `legacy` | MA-cross + MACD + RSI trend mode, RSI/Bollinger mean-reversion in ranging markets | `strategies/indicators.py` |
| `breakout` | Donchian-channel N-bar breakout, confirmed by volume + ADX | `strategies/breakout.py` |
| `volatility` | Bollinger Band squeeze, then trade the direction it breaks out of | `strategies/volatility_squeeze.py` |
| `supertrend` | Single ATR-based Supertrend indicator, trades on direction flips | `strategies/supertrend.py` |
| `ml` | Gradient-boosted classifier on engineered features (returns, RSI, MACD, ADX, ATR, volume z-score) predicting near-term direction | `strategies/ml_classifier.py` |

All strategies are **long-only** (spot account — none of them open a short;
a bearish signal only closes an existing long early).

The `ml` strategy retrains on the trailing `--ml-train-months` of data before
every backtest/walk-forward window and never trains on data from the window
it's tested on, avoiding lookahead bias.

### Pairs / stat-arb (research only)

`strategies/pairs_stat_arb.py` trades the price ratio between two assets
(e.g. BTC vs ETH). **This requires shorting one leg while going long the
other, which a spot account cannot do** — it's not wired into any live
trader, and has its own runner:

```bash
python run_pairs_backtest.py --symbol1 BTC/USDT --symbol2 ETH/USDT --timeframe 1h --start 2023-01-01 --end 2023-10-01
```

Treat its output as research (what a margin/futures account could earn), not
something you can run as-is.

## 7. Recommended workflow

1. **Backtest** across multiple date ranges/timeframes.
2. **Walk-forward validate** — a strategy should hold up across many windows,
   not just one favorable period.
3. **Risk report** — check Sharpe/Calmar against buy-and-hold, not just raw return.
4. **Paper trade** for at least a week to confirm live behavior matches backtests.
5. **Testnet trade** to validate real order execution mechanics.
6. Only after all of the above, and only with money you're fully prepared to
   lose, consider real funds — see below.

## 8. Going live

Real-money trading requires clearing **three independent checks**, by design:

1. `config/settings.py`: `USE_TESTNET = False` — a deliberate code edit, not a flag
2. `.env`: `CONFIRM_REAL_MONEY_TRADING=I_UNDERSTAND_THE_RISK` set explicitly
3. Running with `--real-account` **and** typing an exact confirmation phrase
   at runtime, after being shown your symbol/strategy/amount and a reminder
   of the risk metrics below

Missing any one aborts with no orders placed:

```bash
python -m execution.live_trader --strategy supertrend --real-account
```

### What the testing actually showed

Walk-forward validation across BTC/USDT and ETH/USDT (2021–2025, quarterly
windows) found the legacy strategy roughly breakeven on average, with
Sharpe and Calmar ratios **below** simple buy-and-hold over that period —
despite a dramatically smaller max drawdown (roughly -2 to -3% vs -65 to
-81% during crashes). In plain terms: it protects capital far better than
holding through a crash, but hasn't demonstrated a risk-adjusted edge over
buy-and-hold worth trading real money on yet. Documented here on purpose —
honest evaluation, including negative results, is the point of this project.

## 9. Next steps (not included yet)

- Forex support via OANDA's practice API (same strategy code, new data adapter)
- Mobile dashboard consuming the Flask API endpoints above
- Persistent database (currently paper trading state is a local JSON file)
- `--dry-run` mode for `live_trader.py` (log intended trades without ever calling the exchange)

---

**Disclaimer:** This is an educational project. I am not a financial advisor,
and nothing here is financial advice. Cryptocurrency trading carries
substantial risk of loss. Backtested performance does not guarantee future
results. Test thoroughly and never trade money you cannot afford to lose.
