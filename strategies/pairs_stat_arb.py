"""
Pairs / statistical-arbitrage strategy: trade the SPREAD between two
correlated assets (e.g. BTC/USDT vs ETH/USDT) rather than either one
outright. When the ratio between them stretches unusually far from its
recent average (z-score), bet on it reverting: long the underperformer,
short the outperformer, dollar-neutral.

*** IMPORTANT - READ BEFORE USING ***
Genuine pairs trading REQUIRES shorting one leg while going long the
other. This bot is built for a Binance SPOT account, which cannot short.
This module is therefore RESEARCH-ONLY: it reports what the strategy
would have earned if you COULD hold both legs (e.g. via margin or
futures), so you can decide if it's worth the extra complexity/risk of
a margin or futures account before building real execution for it.
Do not wire this into paper_trader.py or testnet_trader.py as-is - it
does not correspond to any order sequence a spot account can place.
Run it with: python run_pairs_backtest.py
"""
import pandas as pd

ZSCORE_LOOKBACK = 60     # bars used to compute the rolling mean/std of the ratio
ENTRY_ZSCORE = 2.0       # open the spread trade once |z| crosses this
EXIT_ZSCORE = 0.3        # close once the spread has reverted this close to its mean
STOP_ZSCORE = 4.0        # abandon the trade if the spread keeps diverging past this
FEE_PCT = 0.001          # applied per leg, per side (4 fills total per round-trip)
TRADE_NOTIONAL_USDT = 50  # notional PER LEG (so a round-trip risks ~2x this across both legs)


def align_pair(df1, df2):
    """Inner-join two OHLCV frames on timestamp so both legs are compared bar-for-bar."""
    merged = df1[["close"]].join(df2[["close"]], how="inner", lsuffix="_1", rsuffix="_2")
    merged = merged.dropna()
    return merged


def add_spread_indicators(merged):
    df = merged.copy()
    df["ratio"] = df["close_1"] / df["close_2"]
    roll_mean = df["ratio"].rolling(ZSCORE_LOOKBACK).mean()
    roll_std = df["ratio"].rolling(ZSCORE_LOOKBACK).std()
    df["zscore"] = (df["ratio"] - roll_mean) / roll_std
    return df


class PairsBacktester:
    """Self-contained backtest loop for the pair - separate from the main
    single-asset Backtester because a two-legged, dollar-neutral spread
    trade has fundamentally different P&L mechanics (two prices, two
    directions, four fills per round-trip) than a single long position."""

    def __init__(self, merged_df, symbol1, symbol2,
                 starting_balance=1000.0, trade_notional=None, fee_pct=None):
        self.df = add_spread_indicators(merged_df)
        self.symbol1 = symbol1
        self.symbol2 = symbol2
        self.balance = starting_balance
        self.starting_balance = starting_balance
        self.trade_notional = trade_notional or TRADE_NOTIONAL_USDT
        self.fee_pct = fee_pct if fee_pct is not None else FEE_PCT

        self.position = None  # dict: direction ("long_1_short_2" / "long_2_short_1"), entries, amounts
        self.trades = []
        self.total_fees_paid = 0.0

    def run(self):
        min_bars = ZSCORE_LOOKBACK + 2
        for i in range(min_bars, len(self.df)):
            row = self.df.iloc[i]
            if pd.isna(row["zscore"]):
                continue

            if self.position:
                self._check_exit(row)

            if not self.position:
                if row["zscore"] >= ENTRY_ZSCORE:
                    # Leg 1 rich relative to leg 2: short 1, long 2
                    self._enter("short_1_long_2", row)
                elif row["zscore"] <= -ENTRY_ZSCORE:
                    # Leg 1 cheap relative to leg 2: long 1, short 2
                    self._enter("long_1_short_2", row)

        if self.position:
            self._exit(self.df.iloc[-1], "End of backtest")

        return self._report()

    def _enter(self, direction, row):
        entry_fee = self.trade_notional * 2 * self.fee_pct  # two legs opened at once
        self.balance -= entry_fee
        self.total_fees_paid += entry_fee
        self.position = {
            "direction": direction,
            "entry_price_1": row["close_1"],
            "entry_price_2": row["close_2"],
            "entry_zscore": row["zscore"],
            "entry_time": row.name,
        }

    def _check_exit(self, row):
        z = row["zscore"]
        entry_z = self.position["entry_zscore"]
        reverted = (entry_z > 0 and z <= EXIT_ZSCORE) or (entry_z < 0 and z >= -EXIT_ZSCORE)
        blew_through_stop = abs(z) >= STOP_ZSCORE and abs(z) > abs(entry_z)

        if reverted:
            self._exit(row, "Spread reverted to mean")
        elif blew_through_stop:
            self._exit(row, "Stop - spread kept diverging")

    def _exit(self, row, reason):
        p1_entry, p2_entry = self.position["entry_price_1"], self.position["entry_price_2"]
        p1_now, p2_now = row["close_1"], row["close_2"]
        amount_1 = self.trade_notional / p1_entry
        amount_2 = self.trade_notional / p2_entry

        if self.position["direction"] == "long_1_short_2":
            pnl = (p1_now - p1_entry) * amount_1 + (p2_entry - p2_now) * amount_2
        else:
            pnl = (p1_entry - p1_now) * amount_1 + (p2_now - p2_entry) * amount_2

        exit_fee = self.trade_notional * 2 * self.fee_pct
        pnl -= exit_fee
        self.balance += pnl
        self.total_fees_paid += exit_fee

        self.trades.append({
            "direction": self.position["direction"],
            "entry_time": self.position["entry_time"], "exit_time": row.name,
            "entry_zscore": round(self.position["entry_zscore"], 2), "exit_zscore": round(row["zscore"], 2),
            "pnl": round(pnl, 3), "reason": reason,
        })
        self.position = None

    def _report(self):
        wins = [t for t in self.trades if t["pnl"] > 0]
        losses = [t for t in self.trades if t["pnl"] <= 0]
        total_return_pct = ((self.balance - self.starting_balance) / self.starting_balance) * 100
        return {
            "symbol1": self.symbol1, "symbol2": self.symbol2,
            "starting_balance": round(self.starting_balance, 2),
            "final_balance": round(self.balance, 2),
            "total_return_pct": round(total_return_pct, 2),
            "total_trades": len(self.trades),
            "wins": len(wins), "losses": len(losses),
            "win_rate_pct": round(len(wins) / len(self.trades) * 100, 2) if self.trades else 0,
            "total_fees_paid": round(self.total_fees_paid, 2),
            "trades": self.trades,
        }


def print_report(report):
    print("\n" + "=" * 60)
    print(f"PAIRS BACKTEST RESULTS - {report['symbol1']} vs {report['symbol2']}")
    print("(RESEARCH ONLY - requires shorting one leg, not executable on a spot account)")
    print("=" * 60)
    print(f"Starting balance:  ${report['starting_balance']}")
    print(f"Final balance:     ${report['final_balance']}")
    print(f"Total return:      {report['total_return_pct']}%")
    print(f"Total trades:      {report['total_trades']}")
    print(f"Wins / Losses:     {report['wins']} / {report['losses']}")
    print(f"Win rate:          {report['win_rate_pct']}%")
    print(f"Total fees paid:   ${report['total_fees_paid']}")
    print("=" * 60 + "\n")
