"""
Live execution for ANY registered strategy (legacy, breakout, volatility,
supertrend, ml) - testnet by default.

This replaces execution/testnet_trader.py's hardcoded legacy-only signal
with strategies.registry, so --strategy works the same way it does in
run_backtest.py / run_walkforward.py.

For --strategy ml specifically: a model can't be trained on the same data
it's about to trade on (lookahead bias), so this script trains on a
trailing window of real historical data and RETRAINS on a schedule
(--ml-retrain-days, default 30) rather than training once and reusing an
increasingly stale model forever.

REAL-MONEY TRADING IS OFF BY DEFAULT AND DELIBERATELY HARD TO TURN ON.
Three separate things must all be true before a single real order is
placed - see requires_real_account_confirmation() below. Testnet trading
(fake funds, real exchange mechanics) needs none of this and is the
default.

Usage:
    # Testnet - safe, default, no confirmation needed
    python -m execution.live_trader --strategy supertrend
    python -m execution.live_trader --strategy ml --ml-train-months 12 --ml-retrain-days 30

    # Real account - only after you've set USE_TESTNET = False in
    # config/settings.py AND set CONFIRM_REAL_MONEY_TRADING in .env AND
    # pass --real-account AND type the confirmation phrase this asks for.
    python -m execution.live_trader --strategy supertrend --real-account
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import time
from datetime import datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta

from data.fetcher import fetch_ohlcv, fetch_historical_range, get_exchange
from strategies.registry import STRATEGIES, CHOICES
from strategies import ml_classifier
from config import settings


class LiveTrader:
    def __init__(self, strategy_name, ml_train_months=12, ml_retrain_days=30,
                 real_account=False):
        self.strategy_name = strategy_name
        self.ml_train_months = ml_train_months
        self.ml_retrain_days = ml_retrain_days
        self.real_account = real_account

        self.exchange = get_exchange()
        self.position = None

        # Non-ml strategies: bind add_indicators/generate_signal once, up front.
        # ml: these get (re)bound by _retrain_ml_model(), called from run_once().
        self.add_indicators = None
        self.signal_fn = None
        self.min_bars = 200
        self._last_train_time = None

        if strategy_name != "ml":
            spec = STRATEGIES[strategy_name]
            self.add_indicators = spec["add_indicators"]
            self.signal_fn = spec["generate_signal"]
            self.min_bars = spec["min_bars"]

    # ------------------------------------------------------------------
    # ML-specific: train on a trailing window, retrain on a schedule
    # ------------------------------------------------------------------
    def _retrain_ml_model(self):
        now = datetime.now(timezone.utc)
        due = (self._last_train_time is None or
               now - self._last_train_time >= timedelta(days=self.ml_retrain_days))
        if not due:
            return

        train_end = now.strftime("%Y-%m-%d")
        train_start = (now - relativedelta(months=self.ml_train_months)).strftime("%Y-%m-%d")
        self._log(f"Training ML model on {train_start} -> {train_end} "
                   f"({self.ml_train_months} trailing months)...")

        train_df = fetch_historical_range(settings.SYMBOL, settings.TIMEFRAME,
                                           train_start, train_end)
        model, feature_cols = ml_classifier.train_model(train_df)
        if model is None:
            self._log("WARNING: not enough clean training data - keeping previous model "
                       "(or, on first run, staying in HOLD until enough data exists).")
            if self._last_train_time is None:
                # No usable model at all yet - fall back to an always-HOLD signal
                # rather than crashing, so run_forever can keep retrying on schedule.
                self.add_indicators = ml_classifier.add_indicators_for_backtest
                self.signal_fn = lambda df: ("HOLD", "No trained model yet", "ml")
            return

        self.add_indicators = ml_classifier.add_indicators_for_backtest
        self.signal_fn = ml_classifier.build_signal_fn(model, feature_cols)
        self.min_bars = 210
        self._last_train_time = now
        self._log("ML model (re)trained successfully.")

    # ------------------------------------------------------------------
    def _log(self, msg):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tag = "REAL" if self.real_account else "TESTNET"
        print(f"[{timestamp}] [{tag}] {msg}")

    def _place_order(self, side, amount):
        order = self.exchange.create_market_order(settings.SYMBOL, side, amount)
        self._log(f"Order placed: {side.upper()} {amount} {settings.SYMBOL} -> {order.get('id')}")
        return order

    def check_exit(self, price, reason=None):
        entry = self.position["entry_price"]
        change = (price - entry) / entry

        hit_stop = change <= -settings.STOP_LOSS_PCT
        hit_target = change >= settings.TAKE_PROFIT_PCT

        if hit_stop or hit_target or reason:
            exit_reason = reason or ("Stop-loss hit" if hit_stop else "Take-profit hit")
            self._place_order("sell", self.position["amount"])
            self._log(f"EXITED LONG | {exit_reason}")
            self.position = None

    def run_once(self):
        if self.strategy_name == "ml":
            self._retrain_ml_model()

        limit = max(250, self.min_bars + 20)
        df = fetch_ohlcv(limit=limit)
        df = self.add_indicators(df)
        price = df.iloc[-1]["close"]

        if self.position:
            self.check_exit(price)

        signal, reason, mode = self.signal_fn(df)

        if self.position:
            if signal == "SELL":
                self.check_exit(price, reason=f"Signal reversed - {reason}")
            else:
                self._log(f"Monitoring LONG | Price: {price:.2f}")
        else:
            if signal == "BUY":
                amount = round(settings.TRADE_AMOUNT_USDT / price, 6)
                self._place_order("buy", amount)
                self.position = {"side": "long", "entry_price": price, "amount": amount}
                self._log(f"ENTERED LONG at {price:.2f} | {reason}")
            else:
                self._log(f"HOLD at {price:.2f} | {reason}")

    def run_forever(self):
        self._log(f"Starting trader | Strategy: {self.strategy_name} | "
                   f"Symbol: {settings.SYMBOL} | "
                   f"{'*** REAL MONEY ***' if self.real_account else 'testnet (fake funds)'}")
        while True:
            try:
                self.run_once()
            except Exception as e:
                self._log(f"Error: {e}")
            time.sleep(settings.POLL_INTERVAL_SECONDS)


# ----------------------------------------------------------------------
# Real-account gating. All three checks must pass, independently, before
# a single real order can be placed. Each is here so that no single
# mistake (a stray CLI flag, an old .env value, a forgotten settings edit)
# is enough on its own to put real money at risk.
# ----------------------------------------------------------------------
def requires_real_account_confirmation(args):
    if not args.real_account:
        return True  # testnet path - nothing to confirm

    problems = []

    if settings.USE_TESTNET:
        problems.append(
            "config/settings.py still has USE_TESTNET = True. Change it to False "
            "yourself (a deliberate code edit, not a CLI flag) before going live."
        )

    confirm_env = os.getenv("CONFIRM_REAL_MONEY_TRADING", "")
    if confirm_env.strip() != "I_UNDERSTAND_THE_RISK":
        problems.append(
            "Your .env file needs CONFIRM_REAL_MONEY_TRADING=I_UNDERSTAND_THE_RISK "
            "set explicitly (see .env.example)."
        )

    if problems:
        print("Cannot start real-account trading yet:")
        for p in problems:
            print(f"  - {p}")
        return False

    print("=" * 70)
    print("You are about to trade REAL MONEY on a REAL exchange account.")
    print(f"  Symbol:           {settings.SYMBOL}")
    print(f"  Strategy:         {args.strategy}")
    print(f"  Amount per trade: {settings.TRADE_AMOUNT_USDT} USDT")
    print("This bot has no demonstrated risk-adjusted edge on this strategy")
    print("(see your run_risk_report.py output - Sharpe/Calmar were both")
    print("below buy-and-hold). Only proceed with an amount you are fully")
    print("prepared to lose.")
    print("=" * 70)
    expected = f"trade real money on {settings.SYMBOL}"
    typed = input(f"Type exactly \"{expected}\" to continue, or anything else to abort: ")
    if typed.strip() != expected:
        print("Confirmation phrase did not match - aborting. Nothing was started.")
        return False

    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", default="legacy", choices=CHOICES,
                         help="Which strategy to trade: " + ", ".join(CHOICES))
    parser.add_argument("--ml-train-months", type=int, default=12,
                         help="--strategy ml only: trailing months of data used per (re)training")
    parser.add_argument("--ml-retrain-days", type=int, default=30,
                         help="--strategy ml only: how often to retrain on fresh trailing data")
    parser.add_argument("--real-account", action="store_true",
                         help="Trade on the real exchange account instead of testnet. "
                              "Gated behind extra confirmation - see README.")
    args = parser.parse_args()

    if not settings.BINANCE_API_KEY or not settings.BINANCE_API_SECRET:
        print("ERROR: Set BINANCE_API_KEY and BINANCE_API_SECRET in your .env file first.")
        print("Testnet keys: https://testnet.binance.vision/  "
              "Real-account keys: your exchange account's API management page.")
        return

    if not requires_real_account_confirmation(args):
        return

    trader = LiveTrader(
        strategy_name=args.strategy,
        ml_train_months=args.ml_train_months,
        ml_retrain_days=args.ml_retrain_days,
        real_account=args.real_account,
    )
    trader.run_forever()


if __name__ == "__main__":
    main()
