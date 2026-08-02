"""
Risk-adjusted comparison: chains walk-forward windows into ONE continuous
equity curve (each window starts from the previous window's ending balance,
instead of resetting to $1000 like run_walkforward.py does) and compares
max drawdown + annualized Sharpe ratio against buy-and-hold over the same
period. Total return alone hides how bumpy the ride was to get there - this
is the number that actually tells you if a strategy is worth running.

Usage:
    python run_risk_report.py --strategy ml --symbol BTC/USDT --timeframe 1h --start 2021-01-01 --end 2025-06-01 --ml-train-months 12
"""
import argparse
import numpy as np
import pandas as pd
from data.fetcher import fetch_historical_range
from run_walkforward import generate_windows, run_one_window
from config import settings


def compute_metrics(equity_series):
    """equity_series: pandas Series of equity values, indexed by timestamp, sorted."""
    equity_series = equity_series.sort_index()
    equity_series = equity_series[~equity_series.index.duplicated(keep="last")]

    total_return_pct = (equity_series.iloc[-1] / equity_series.iloc[0] - 1) * 100

    running_peak = equity_series.cummax()
    drawdown = (equity_series - running_peak) / running_peak
    max_drawdown_pct = drawdown.min() * 100

    daily = equity_series.resample("D").last().dropna()
    daily_returns = daily.pct_change().dropna()
    if len(daily_returns) > 1 and daily_returns.std() > 0:
        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(365)
    else:
        sharpe = 0.0

    calmar = (total_return_pct / abs(max_drawdown_pct)) if max_drawdown_pct != 0 else 0.0

    return {
        "total_return_pct": round(total_return_pct, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "sharpe": round(sharpe, 2),
        "calmar": round(calmar, 2),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default="2025-06-01")
    parser.add_argument("--window-months", type=int, default=3)
    parser.add_argument("--strategy", default="ml")
    parser.add_argument("--ml-train-months", type=int, default=12)
    args = parser.parse_args()

    starting_balance = settings.PAPER_STARTING_BALANCE
    running_balance = starting_balance
    master_equity = []
    total_trades = 0
    skipped = 0

    windows = generate_windows(args.start, args.end, args.window_months)
    print(f"Chaining {len(windows)} walk-forward windows into one continuous "
          f"equity curve ({args.strategy}, {args.symbol} {args.timeframe})...\n")

    for win_start, win_end in windows:
        print(f"Window {win_start} to {win_end}... (balance carried in: ${running_balance:.2f})")
        try:
            report, skip_reason = run_one_window(args, win_start, win_end, starting_balance=running_balance)
        except Exception as e:
            print(f"  Error: {e} - carrying balance forward unchanged")
            skipped += 1
            continue

        if skip_reason:
            print(f"  Skipped - {skip_reason}")
            skipped += 1
            continue

        running_balance = report["final_balance"]
        total_trades += report["total_trades"]
        master_equity.extend(report["equity_curve"])

    if len(master_equity) < 10:
        print("\nNot enough equity data collected to compute a risk report.")
        return

    strat_equity = pd.Series(
        {pd.Timestamp(e["timestamp"]): e["equity"] for e in master_equity}
    )
    strat_metrics = compute_metrics(strat_equity)

    print("\nFetching full-range price data for the buy-and-hold comparison...")
    full_df = fetch_historical_range(args.symbol, args.timeframe, args.start, args.end)
    bh_equity = starting_balance * (full_df["close"] / full_df["close"].iloc[0])
    bh_equity.index = full_df.index
    bh_metrics = compute_metrics(bh_equity)

    print("\n" + "=" * 70)
    print(f"RISK REPORT - {args.strategy} vs buy-and-hold - {args.symbol} ({args.timeframe})")
    print(f"{args.start} to {args.end}")
    print("=" * 70)
    print(f"{'Metric':<28} {'Strategy':<16} {'Buy & Hold':<16}")
    print("-" * 70)
    print(f"{'Total return %':<28} {strat_metrics['total_return_pct']:<16} {bh_metrics['total_return_pct']:<16}")
    print(f"{'Max drawdown %':<28} {strat_metrics['max_drawdown_pct']:<16} {bh_metrics['max_drawdown_pct']:<16}")
    print(f"{'Sharpe (annualized)':<28} {strat_metrics['sharpe']:<16} {bh_metrics['sharpe']:<16}")
    print(f"{'Calmar (return/drawdown)':<28} {strat_metrics['calmar']:<16} {bh_metrics['calmar']:<16}")
    print("-" * 70)
    print(f"Total trades across all windows: {total_trades}  (windows skipped: {skipped})")
    print("=" * 70)
    print("\nWhy this matters: total return alone can't tell you if a strategy is")
    print("worth running - a strategy with a much smaller return but a MUCH")
    print("smaller max drawdown and higher Sharpe/Calmar can be the better bet")
    print("for actual money, even though buy-and-hold usually wins on raw return")
    print("during a historic bull run like 2021-2025 crypto.\n")


if __name__ == "__main__":
    main()
