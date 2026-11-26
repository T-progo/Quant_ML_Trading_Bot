<div align="center">

# 🤖 Quant Trading Bot

**A multi-strategy crypto trading bot built on rigorous backtesting — not guesswork.**

[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Binance](https://img.shields.io/badge/exchange-Binance-F0B90B?logo=binance&logoColor=white)](https://www.binance.com/)
[![License](https://img.shields.io/badge/license-MIT-green)](#)
[![Status](https://img.shields.io/badge/status-educational%20project-orange)](#-going-live)

Trend-following • Mean-reversion • Breakout • SuperTrend • Machine Learning
Walk-forward validation • Sharpe/Calmar risk reporting • Paper & testnet execution

</div>

---

## ✨ Features

| | |
|---|---|
| 🎯 **5 strategies** | Legacy (MA/RSI/MACD), breakout, volatility squeeze, SuperTrend, and a gradient-boosted ML classifier — swap between them with one CLI flag |
| 📊 **Real backtesting** | Trading fees simulated, every result benchmarked against buy-and-hold, not judged in isolation |
| 🔁 **Walk-forward validation** | Tests across rolling time windows instead of one cherry-picked period — the standard defense against overfitting |
| 📈 **Risk-adjusted reporting** | Sharpe ratio, Calmar ratio, max drawdown — how professionals actually judge a strategy |
| 📝 **Paper trading** | Simulated trades on live data, zero risk |
| 🧪 **Testnet execution** | Real order mechanics on Binance's sandbox — no real funds |
| 🔒 **Live execution, triple-gated** | Real-money trading requires three independent, deliberate confirmations |
| 🌐 **Flask API** | Check bot status and signals from anywhere |

---

## 📁 Project Structure

```
quant-trading-bot/
├── config/settings.py         # all tunable parameters
├── data/fetcher.py            # OHLCV candle data via ccxt (Binance)
├── strategies/
│   ├── indicators.py          # legacy: MA/RSI/MACD trend + mean-reversion mode
│   ├── breakout.py            # Donchian-channel breakout
│   ├── volatility_squeeze.py  # Bollinger Band squeeze breakout
│   ├── supertrend.py          # ATR-based Supertrend
│   ├── ml_classifier.py       # gradient-boosted classifier, scheduled retraining
│   ├── pairs_stat_arb.py      # BTC/ETH pairs trading (research only)
│   └── registry.py            # strategy lookup by name
├── backtest/backtester.py     # fee-aware backtest engine + buy-and-hold benchmark
├── execution/
│   ├── paper_trader.py        # simulated trades on live data
│   ├── testnet_trader.py      # legacy strategy, real orders on testnet
│   └── live_trader.py         # ALL strategies; testnet by default, real-account
│                               # trading gated behind 3 confirmations
├── api/app.py                 # Flask API
├── run_backtest.py
├── run_walkforward.py
├── run_comparison.py
├── run_risk_report.py
├── run_pairs_backtest.py
└── check_trade.py             # "should I trade right now?" on demand
```

---

## 🚀 Quick Start

```bash
# 1. Clone and enter the project
git clone https://github.com/Shafqat388/quant-trading-bot.git
cd quant-trading-bot

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\Activate.ps1        # Windows
# source venv/bin/activate       # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure API keys
copy .env.example .env           # Windows
# cp .env.example .env           # Mac/Linux
```

Open `.env` and add your **Binance Testnet** keys from [testnet.binance.vision](https://testnet.binance.vision/).

> **Note:** uses `pandas-ta-classic`, not the original `pandas-ta` (discontinued on PyPI, now requires Python 3.12+). Same function calls, different import name.

---

## 🧭 Usage

### Backtest a strategy
```bash
python run_backtest.py --strategy legacy --symbol BTC/USDT --timeframe 1h --start 2024-01-01 --end 2025-06-01
```
Reports final balance, win rate, avg win/loss, fees paid — and a **buy-and-hold comparison** on every run.

### Walk-forward validation
```bash
python run_walkforward.py --strategy legacy --symbol BTC/USDT --timeframe 1h --start 2021-01-01 --end 2025-06-01 --window-months 3
```
Splits the range into sequential windows and backtests each separately. A single good backtest can be luck — consistency across many windows is the real signal.

### Risk-adjusted report
```bash
python run_risk_report.py --strategy ml --symbol BTC/USDT --timeframe 1h --start 2021-01-01 --end 2025-06-01 --ml-train-months 12
```
Sharpe, Calmar, and max drawdown vs. buy-and-hold — win rate alone doesn't tell you if the risk was worth it.

### Check the current signal, no trading
```bash
python check_trade.py --symbol BTC/USDT --timeframe 1h
```

### Paper trade (fake money, live prices)
```bash
python execution/paper_trader.py
```

### Live/testnet trader — any strategy
```bash
python -m execution.live_trader --strategy supertrend
python -m execution.live_trader --strategy ml --ml-train-months 12 --ml-retrain-days 30
```

### Flask API
```bash
python api/app.py
```
| Endpoint | What it does |
|---|---|
| `GET /health` | Confirm the API is running |
| `GET /signal` | Current price + BUY/SELL/HOLD + strategy mode |
| `GET /paper/status` | Paper trading balance & trade log |
| `POST /paper/tick` | Manually trigger one check |
| `GET /backtest?symbol=BTC/USDT&timeframe=15m&start=2025-01-01` | Run a backtest via API |

---

## ⚙️ Available Strategies

| Flag | Idea | File |
|---|---|---|
| `legacy` | MA-cross + MACD + RSI trend mode, RSI/Bollinger mean-reversion when ranging | `strategies/indicators.py` |
| `breakout` | Donchian-channel N-bar breakout, confirmed by volume + ADX | `strategies/breakout.py` |
| `volatility` | Bollinger Band squeeze, trades the breakout direction | `strategies/volatility_squeeze.py` |
| `supertrend` | ATR-based Supertrend, trades on direction flips | `strategies/supertrend.py` |
| `ml` | Gradient-boosted classifier on engineered features (returns, RSI, MACD, ADX, ATR, volume z-score) | `strategies/ml_classifier.py` |

All strategies are **long-only** (spot account — a bearish signal only closes an existing long, never opens a short).

The `ml` strategy retrains on the trailing `--ml-train-months` of data before every window and never trains on data it's then tested on, avoiding lookahead bias.

<details>
<summary><b>Pairs / stat-arb (research only, click to expand)</b></summary>

<br>

`strategies/pairs_stat_arb.py` trades the price ratio between two assets (e.g. BTC vs ETH). This requires shorting one leg while going long the other — **not possible on a spot account** — so it isn't wired into any live trader and has its own runner:

```bash
python run_pairs_backtest.py --symbol1 BTC/USDT --symbol2 ETH/USDT --timeframe 1h --start 2023-01-01 --end 2023-10-01
```

Treat its output as research (what a margin/futures account could earn), not something runnable as-is.

</details>

---

## 🛤️ Recommended Workflow

```
Backtest → Walk-forward validate → Risk report → Paper trade → Testnet trade → (maybe) Real funds
```

1. **Backtest** across multiple date ranges/timeframes
2. **Walk-forward validate** — should hold up across many windows, not one lucky period
3. **Risk report** — check Sharpe/Calmar against buy-and-hold, not just raw return
4. **Paper trade** for at least a week to confirm live behavior matches backtests
5. **Testnet trade** to validate real order execution mechanics
6. Only then, with money you're fully prepared to lose — see below

---

## 🔒 Going Live

Real-money trading requires clearing **three independent checks**, by design:

1. `config/settings.py` → `USE_TESTNET = False` — a deliberate code edit, not a flag
2. `.env` → `CONFIRM_REAL_MONEY_TRADING=I_UNDERSTAND_THE_RISK` set explicitly
3. Run with `--real-account` **and** type an exact confirmation phrase at runtime, after being shown your symbol/strategy/amount and the risk metrics below

Missing any one aborts with no orders placed:

```bash
python -m execution.live_trader --strategy supertrend --real-account
```

### 📉 What the testing actually showed

Walk-forward validation across BTC/USDT and ETH/USDT (2021–2025, quarterly windows) found the legacy strategy roughly **breakeven on average**, with Sharpe and Calmar ratios **below** simple buy-and-hold over that period — despite a dramatically smaller max drawdown (≈ -2 to -3% vs. -65 to -81% during crashes).

**In plain terms:** it protects capital far better than holding through a crash, but hasn't demonstrated a risk-adjusted edge over buy-and-hold worth trading real money on yet. Documented here on purpose — honest evaluation, including negative results, is the point of this project.

---

## 🗺️ Roadmap

- [ ] Forex support via OANDA's practice API
- [ ] Mobile dashboard consuming the Flask API
- [ ] Persistent database (currently JSON-file based)
- [ ] `--dry-run` mode for `live_trader.py`

---

## ⚠️ Disclaimer

This project is for educational purposes. I am not a financial advisor, and nothing here is financial advice. Cryptocurrency trading carries substantial risk of loss. Backtested performance does not guarantee future results. Test thoroughly and never trade money you cannot afford to lose.

<div align="center">


</div>
