"""
Backtesting engine: replays historical candles bar-by-bar through the strategy,
simulating trades with stop-loss/trailing-stop (or fixed take-profit), and
reports performance stats including fees and a buy-and-hold comparison.

Strategy-agnostic: pass any (add_indicators_fn, signal_fn) pair matching the
legacy contract - add_indicators_fn(df) -> df with indicator columns added,
signal_fn(window_df) -> (signal, reason, mode) where signal is
"BUY" / "SELL" / "HOLD". Defaults to the original MA/RSI/MACD/BB strategy
for backward compatibility.
"""
from strategies.indicators import add_indicators, generate_signal
from config import settings


class Backtester:
    def __init__(self, df, starting_balance=None, stop_loss_pct=None, take_profit_pct=None,
                 fee_pct=None, use_trailing_stop=None, trailing_stop_pct=None, use_atr_stops=None,
                 add_indicators_fn=None, signal_fn=None, min_bars=None):
        self.add_indicators_fn = add_indicators_fn or add_indicators
        self.signal_fn = signal_fn or generate_signal
        self.df = self.add_indicators_fn(df)
        self.min_bars_override = min_bars
        self.balance = starting_balance or settings.PAPER_STARTING_BALANCE
        self.starting_balance = self.balance
        self.stop_loss_pct = stop_loss_pct or settings.STOP_LOSS_PCT
        self.take_profit_pct = take_profit_pct or settings.TAKE_PROFIT_PCT
        self.fee_pct = fee_pct if fee_pct is not None else settings.TRADING_FEE_PCT
        self.use_trailing_stop = use_trailing_stop if use_trailing_stop is not None else settings.USE_TRAILING_STOP
        self.trailing_stop_pct = trailing_stop_pct or settings.TRAILING_STOP_PCT
        self.use_atr_stops = use_atr_stops if use_atr_stops is not None else settings.USE_ATR_STOPS

        self.position = None  # dict: entry_price, amount, side, best_price, stop_pct, trail_pct
        self.trades = []
        self.equity_curve = []
        self.total_fees_paid = 0.0

    def run(self):
        min_bars = self.min_bars_override or (max(
            settings.SLOW_MA, settings.MACD_SLOW, settings.BB_PERIOD,
            settings.TREND_MA, settings.ADX_PERIOD, settings.ATR_PERIOD,
        ) + 2)
        min_bars = min(min_bars, max(len(self.df) - 1, 0))

        for i in range(min_bars, len(self.df)):
            window = self.df.iloc[: i + 1]
            curr = window.iloc[-1]
            price = curr["close"]
            timestamp = window.index[-1]

            if self.position:
                self._check_exit(price, timestamp)

            signal, reason, mode = self.signal_fn(window)

            if self.position:
                # Still holding after the stop/trailing check - a fresh SELL
                # signal means the model now thinks price is heading down,
                # so exit the long early instead of riding it out.
                if signal == "SELL":
                    self._exit(price, timestamp, f"Signal reversed - {reason}")
            else:
                # Spot account: there is no short-selling. Only BUY opens a
                # position; a SELL signal with no existing position is a
                # no-op (nothing to sell, nothing to short).
                if signal == "BUY":
                    self._enter("long", price, timestamp, reason, curr.get("atr"), mode)

            equity = self.balance
            if self.position:
                equity += self._unrealized_pnl(price)
            self.equity_curve.append({"timestamp": timestamp, "equity": equity})

        if self.position:
            self._exit(self.df.iloc[-1]["close"], self.df.index[-1], "End of backtest")

        return self._report()

    def _enter(self, side, price, timestamp, reason, atr_value=None, mode="trend"):
        # side is always "long" now - spot accounts can't hold a short position.
        amount = settings.TRADE_AMOUNT_USDT / price
        entry_fee = settings.TRADE_AMOUNT_USDT * self.fee_pct
        self.balance -= entry_fee
        self.total_fees_paid += entry_fee

        if mode == "mean_reversion":
            # Ranging-market trades use fixed, tighter stop/target - these
            # moves are typically smaller than trend moves, and there's no
            # trend to trail, so a simple fixed take-profit makes more sense.
            stop_pct = settings.MR_STOP_LOSS_PCT
            trail_pct = 0.0
            use_trailing = False
            take_profit_pct = settings.MR_TAKE_PROFIT_PCT
        elif self.use_atr_stops and atr_value and atr_value > 0 and price > 0:
            # Trend-mode: ATR-based sizing scales the stop/trail distance to
            # actual recent volatility instead of one fixed % for every trade.
            stop_pct = (atr_value * settings.ATR_STOP_MULT) / price
            trail_pct = (atr_value * settings.ATR_TRAIL_MULT) / price
            use_trailing = self.use_trailing_stop
            take_profit_pct = self.take_profit_pct
        else:
            stop_pct = self.stop_loss_pct
            trail_pct = self.trailing_stop_pct
            use_trailing = self.use_trailing_stop
            take_profit_pct = self.take_profit_pct

        self.position = {
            "side": side, "entry_price": price, "amount": amount,
            "entry_time": timestamp, "best_price": price,
            "stop_pct": stop_pct, "trail_pct": trail_pct,
            "use_trailing": use_trailing, "take_profit_pct": take_profit_pct,
            "mode": mode,
        }
        self.trades.append({
            "type": "ENTRY", "side": side, "price": price, "mode": mode,
            "timestamp": timestamp, "reason": reason, "fee": entry_fee,
            "stop_pct": round(stop_pct * 100, 3),
        })

    def _check_exit(self, price, timestamp):
        entry = self.position["entry_price"]
        side = self.position["side"]
        stop_pct = self.position["stop_pct"]
        trail_pct = self.position["trail_pct"]
        use_trailing = self.position["use_trailing"]
        take_profit_pct = self.position["take_profit_pct"]

        # Track the best price seen so far (for trailing stop)
        self.position["best_price"] = max(self.position["best_price"], price)

        change = (price - entry) / entry

        # Fixed stop-loss always applies first (protects against a bad move right away)
        if change <= -stop_pct:
            self._exit(price, timestamp, "Stop-loss hit")
            return

        if use_trailing:
            # Once price has moved favorably by at least the stop distance,
            # trailing "activates": the effective stop moves up to breakeven
            # and then trails the best price seen. This guarantees that once
            # trailing is active, the worst case is breakeven, never a fresh
            # loss mislabeled as "locking in profit."
            best = self.position["best_price"]
            favorable_move = (best - entry) / entry
            activated = favorable_move >= stop_pct

            if activated:
                trail_level = best * (1 - trail_pct)
                effective_stop = max(entry, trail_level)  # never worse than breakeven
                if price <= effective_stop:
                    self._exit(price, timestamp, "Trailing stop hit")
        else:
            if change >= take_profit_pct:
                self._exit(price, timestamp, "Take-profit hit")

    def _exit(self, price, timestamp, reason):
        pnl = self._unrealized_pnl(price)
        exit_value = self.position["amount"] * price
        exit_fee = exit_value * self.fee_pct
        pnl -= exit_fee  # fee eats into the realized profit/loss

        self.balance += pnl
        self.total_fees_paid += exit_fee
        self.trades.append({
            "type": "EXIT", "side": self.position["side"], "price": price,
            "mode": self.position.get("mode", "trend"),
            "timestamp": timestamp, "reason": reason, "pnl": pnl, "fee": exit_fee,
        })
        self.position = None

    def _unrealized_pnl(self, price):
        entry = self.position["entry_price"]
        amount = self.position["amount"]
        return (price - entry) * amount

    def _report(self):
        exits = [t for t in self.trades if t["type"] == "EXIT"]
        wins = [t for t in exits if t["pnl"] > 0]
        losses = [t for t in exits if t["pnl"] <= 0]

        total_return_pct = ((self.balance - self.starting_balance) / self.starting_balance) * 100

        avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0

        first_price = self.df.iloc[0]["close"]
        last_price = self.df.iloc[-1]["close"]
        buy_hold_return_pct = ((last_price - first_price) / first_price) * 100

        # Breakdown by mode, so we can see whether each sub-strategy is
        # actually contributing to (or dragging on) results. Modes are
        # whatever the strategy's signal_fn returns - not fixed to the
        # legacy trend/mean_reversion pair, so any strategy's labels work.
        modes_seen = sorted(set(t.get("mode", "default") for t in exits)) or ["default"]
        by_mode = {}
        for m in modes_seen:
            mode_exits = [t for t in exits if t.get("mode", "default") == m]
            mode_wins = [t for t in mode_exits if t["pnl"] > 0]
            by_mode[m] = {
                "trades": len(mode_exits),
                "wins": len(mode_wins),
                "win_rate_pct": round(len(mode_wins) / len(mode_exits) * 100, 2) if mode_exits else 0,
                "total_pnl": round(sum(t["pnl"] for t in mode_exits), 3),
            }

        return {
            "starting_balance": round(self.starting_balance, 2),
            "final_balance": round(self.balance, 2),
            "total_return_pct": round(total_return_pct, 2),
            "total_trades": len(exits),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": round(len(wins) / len(exits) * 100, 2) if exits else 0,
            "avg_win": round(avg_win, 3),
            "avg_loss": round(avg_loss, 3),
            "total_fees_paid": round(self.total_fees_paid, 2),
            "buy_hold_return_pct": round(buy_hold_return_pct, 2),
            "beat_buy_hold": total_return_pct > buy_hold_return_pct,
            "by_mode": by_mode,
            "trades": self.trades,
            "equity_curve": self.equity_curve,
        }


def print_report(report):
    print("\n" + "=" * 50)
    print("BACKTEST RESULTS")
    print("=" * 50)
    print(f"Starting balance:  ${report['starting_balance']}")
    print(f"Final balance:     ${report['final_balance']}")
    print(f"Total return:      {report['total_return_pct']}%")
    print(f"Total trades:      {report['total_trades']}")
    print(f"Wins / Losses:     {report['wins']} / {report['losses']}")
    print(f"Win rate:          {report['win_rate_pct']}%")
    print(f"Avg win / loss:    ${report['avg_win']} / ${report['avg_loss']}")
    print(f"Total fees paid:   ${report['total_fees_paid']}")
    print("-" * 50)
    print("By mode:")
    for mode, stats in report["by_mode"].items():
        label = mode.replace("_", " ").title()
        print(f"  {label:<20} {stats['trades']} trades, {stats['win_rate_pct']}% win rate, ${stats['total_pnl']} total P/L")
    print("-" * 50)
    print(f"Buy & hold return: {report['buy_hold_return_pct']}%  (if you'd just bought and held instead)")
    if report["beat_buy_hold"]:
        print("Result: Strategy BEAT buy-and-hold \u2714")
    else:
        print("Result: Strategy did NOT beat buy-and-hold \u2718")
    print("=" * 50 + "\n")
