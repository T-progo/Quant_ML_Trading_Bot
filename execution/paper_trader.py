"""
Paper trading: runs the strategy against LIVE market data but simulates
trades with fake money. No real orders are ever placed. Good for validating
a strategy in real-time conditions before risking testnet/real funds.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import json
from datetime import datetime
from data.fetcher import fetch_ohlcv
from strategies.indicators import add_indicators, generate_signal
from config import settings

STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "logs", "paper_trader_state.json")


class PaperTrader:
    def __init__(self):
        self.balance = settings.PAPER_STARTING_BALANCE
        self.position = None
        self.trade_log = []
        self._load_state()

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
                self.balance = state.get("balance", self.balance)
                self.position = state.get("position")
                self.trade_log = state.get("trade_log", [])

    def _save_state(self):
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump({
                "balance": self.balance,
                "position": self.position,
                "trade_log": self.trade_log,
            }, f, indent=2, default=str)

    def _log(self, msg):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {msg}")

    def check_exit(self, price):
        entry = self.position["entry_price"]
        change = (price - entry) / entry

        if change <= -settings.STOP_LOSS_PCT:
            self._exit(price, "Stop-loss hit")
        elif change >= settings.TAKE_PROFIT_PCT:
            self._exit(price, "Take-profit hit")

    def _enter(self, side, price, reason):
        # side is always "long" - this is a spot account, there is no shorting.
        amount = settings.TRADE_AMOUNT_USDT / price
        self.position = {"side": side, "entry_price": price, "amount": amount,
                          "entry_time": str(datetime.now())}
        self.trade_log.append({"type": "ENTRY", "side": side, "price": price,
                                "reason": reason, "timestamp": str(datetime.now())})
        self._log(f"ENTERED {side.upper()} at {price:.2f} | {reason}")

    def _exit(self, price, reason):
        entry = self.position["entry_price"]
        amount = self.position["amount"]
        pnl = (price - entry) * amount
        self.balance += pnl
        self.trade_log.append({"type": "EXIT", "side": side, "price": price,
                                "pnl": pnl, "reason": reason, "timestamp": str(datetime.now())})
        self._log(f"EXITED {side.upper()} at {price:.2f} | PnL: {pnl:+.2f} | Balance: {self.balance:.2f} | {reason}")
        self.position = None

    def run_once(self):
        """Fetch latest data, check for signals/exits. Call this in a loop."""
        df = fetch_ohlcv(limit=200)
        df = add_indicators(df)
        price = df.iloc[-1]["close"]

        if self.position:
            self.check_exit(price)

        signal, reason, mode = generate_signal(df)

        if self.position:
            if signal == "SELL":
                self._exit(price, f"Signal reversed - {reason}")
            else:
                self._log(f"Monitoring {self.position['side'].upper()} position | Price: {price:.2f}")
        else:
            if signal == "BUY":
                self._enter("long", price, reason)
            else:
                # Spot account: no shorting. A SELL signal with no open
                # position is a no-op - nothing to sell, nothing to short.
                self._log(f"HOLD at {price:.2f} | {reason}")

        self._save_state()

    def run_forever(self):
        self._log(f"Starting paper trader | Balance: ${self.balance:.2f} | Symbol: {settings.SYMBOL}")
        while True:
            try:
                self.run_once()
            except Exception as e:
                self._log(f"Error: {e}")
            time.sleep(settings.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    trader = PaperTrader()
    trader.run_forever()
