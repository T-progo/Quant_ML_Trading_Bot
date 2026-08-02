"""
Central configuration for the trading bot.
Loads sensitive values (API keys) from a .env file - never hardcode keys here.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Binance Testnet API credentials ---
# Get these from https://testnet.binance.vision/ (login with GitHub)
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
USE_TESTNET = True  # Keep True until you're ready for real funds.
# NOTE: execution/live_trader.py --real-account will refuse to run against
# real funds until this is manually set to False here AND
# CONFIRM_REAL_MONEY_TRADING is set in .env AND you type the runtime
# confirmation phrase it asks for. Flipping just this flag is not enough.

# --- Trading pair & timeframe ---
SYMBOL = os.getenv("SYMBOL", "BTC/USDT")
TIMEFRAME = os.getenv("TIMEFRAME", "15m")   # e.g. 1m, 5m, 15m, 1h, 4h, 1d

# --- Strategy parameters ---
USE_TREND_MODE = True  # set False to disable trend-following entirely and
                        # isolate mean-reversion performance (bot HOLDs during
                        # strong-trend periods instead of taking trend trades)
FAST_MA = 9
SLOW_MA = 21
TREND_MA = 200  # only trade in the direction of this longer-term trend
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_STD = 2
ADX_PERIOD = 14
ADX_MIN_STRENGTH = 20  # only trade when trend strength (ADX) is above this - filters out choppy/ranging markets
ATR_PERIOD = 14
USE_ATR_STOPS = True       # scale stop-loss/trailing distance to actual market volatility instead of a fixed %
ATR_STOP_MULT = 1.5        # stop-loss = entry price -/+ (ATR * this multiplier)
ATR_TRAIL_MULT = 2.5       # trailing stop distance = ATR * this multiplier (wider than the initial stop,
                            # so winners get more room to run once in profit)

# --- Mean-reversion mode (used when ADX shows a WEAK trend, i.e. ranging market) ---
# Rationale: the trend-following rules above deliberately sit out when ADX is
# low (choppy/ranging conditions). Crypto spends a lot of its time ranging,
# so this is a genuinely different, separate set of rules for that condition
# instead of just doing nothing.
USE_MEAN_REVERSION = True
MR_RSI_OVERSOLD = 25    # more extreme than the trend-mode RSI thresholds - mean reversion wants stronger extremes
MR_RSI_OVERBOUGHT = 75
MR_TAKE_PROFIT_PCT = 0.015  # ranges are smaller moves than trends, so a smaller fixed target
MR_STOP_LOSS_PCT = 0.015    # tight risk since we're fighting momentum, not following it

# --- Trading fees (Binance spot standard rate is 0.1% per side) ---
TRADING_FEE_PCT = 0.001  # 0.1% - charged on both entry and exit
TRADE_AMOUNT_USDT = float(os.getenv("TRADE_AMOUNT_USDT", "50"))  # per trade
STOP_LOSS_PCT = 0.02      # 2% - fallback used only if ATR-based stops are off
TAKE_PROFIT_PCT = 0.04    # 4% - fallback used only if ATR-based stops are off
USE_TRAILING_STOP = True
TRAILING_STOP_PCT = 0.015  # fallback trailing distance if ATR-based stops are off
MAX_OPEN_POSITIONS = 1

# --- ATR-based dynamic risk management (recommended - adapts to volatility) ---
# Fixed % stops treat a calm day and a wild day the same, which tends to make
# average wins and average losses roughly equal size (~breakeven after fees).
# ATR-based stops size the stop/trail distance to actual recent volatility,
# giving a more favorable risk:reward per trade.
USE_ATR_STOPS = True
ATR_PERIOD = 14
ATR_STOP_MULTIPLIER = 1.5       # stop-loss distance = 1.5x ATR
ATR_ACTIVATION_MULTIPLIER = 1.5  # trailing activates once profit >= 1.5x ATR (matches stop distance)
ATR_TRAIL_MULTIPLIER = 2.5       # once activated, trail by 2.5x ATR - wider than the stop,
                                  # giving winners more room to run before locking in

# --- Paper trading ---
PAPER_STARTING_BALANCE = float(os.getenv("PAPER_STARTING_BALANCE", "1000"))

# --- Bot loop ---
POLL_INTERVAL_SECONDS = 60  # how often the live loop checks for signals

# --- Flask API ---
API_HOST = "0.0.0.0"
API_PORT = 5000
