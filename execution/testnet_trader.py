"""
Live execution on Binance TESTNET. This places REAL orders, but against
testnet (fake funds, real exchange behavior). Do not switch USE_TESTNET
to False in settings.py until you fully trust this bot with real money.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from datetime import datetime
from data.fetcher import fetch_ohlcv, get_exchange
from strategies.indicators import add_indicators, generate_signal
from config import settings


class TestnetTrader:
    def __init__(self):
        self.exchange = get_exchange()
        self.position = None  # tracked locally; could also query exchange balance

    def _log(self, msg):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {msg}")

    def _place_order(self, side, amount):
        """side: 'buy' or 'sell'. Places a market order on testnet."""
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
            # Long-only on spot: closing a long always means selling what we hold.
            self._place_order("sell", self.position["amount"])
            self._log(f"EXITED LONG | {exit_reason}")
            self.position = None

    def run_once(self):
        df = fetch_ohlcv(limit=200)
        df = add_indicators(df)
        price = df.iloc[-1]["close"]

        if self.position:
            self.check_exit(price)

        signal, reason, mode = generate_signal(df)

        if self.position:
            # Still holding after the stop/target check above - a fresh SELL
            # signal means exit the long early instead of opening a short
            # (spot accounts can't hold a short position at all).
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
                # Spot account: no shorting. A SELL signal with no open
                # position is a no-op - nothing to sell, nothing to short.
                self._log(f"HOLD at {price:.2f} | {reason}")

    def run_forever(self):
        self._log(f"Starting TESTNET trader | Symbol: {settings.SYMBOL} | LIVE ORDERS ON TESTNET")
        while True:
            try:
                self.run_once()
            except Exception as e:
                self._log(f"Error: {e}")
            time.sleep(settings.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    if not settings.BINANCE_API_KEY or not settings.BINANCE_API_SECRET:
        print("ERROR: Set BINANCE_API_KEY and BINANCE_API_SECRET in your .env file first.")
        print("Get testnet keys from https://testnet.binance.vision/")
    else:
        trader = TestnetTrader()
        trader.run_forever()
