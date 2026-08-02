"""
Walk-forward validation: splits a long historical range into sequential,
non-overlapping windows (e.g. every 3 months) and runs a separate backtest
on each one. This is a stronger check than picking a couple of known
good/bad periods after the fact - it shows whether the strategy's behavior
is CONSISTENT over time, or whether earlier results were partly luck/overfit
to a specific period.

Usage:
    python run_walkforward.py
    python run_walkforward.py --symbol BTC/USDT --timeframe 1h --start 2021-01-01 --end 2025-06-01 --window-months 3
"""
import argparse
from datetime import datetime
from dateutil.relativedelta import relativedelta
from data.fetcher import fetch_historical_range
from backtest.backtester import Backtester
from strategies.registry import STRATEGIES, CHOICES
from strategies import ml_classifier
from config import settings


def generate_windows(start_str, end_str, window_months):
    start = datetime.strptime(start_str, "%Y-%m-%d")
    end = datetime.strptime(end_str, "%Y-%m-%d")
    windows = []
    current = start
    while current < end:
        window_end = min(current + relativedelta(months=window_months), end)
        windows.append((current.strftime("%Y-%m-%d"), window_end.strftime("%Y-%m-%d")))
        current = window_end
    return windows


def run_one_window(args, win_start, win_end, starting_balance=None):
    df = fetch_historical_range(args.symbol, args.timeframe, win_start, win_end)
    if len(df) < 250:
        return None, f"not enough data ({len(df)} candles)"

    if args.strategy == "ml":
        # Retrain fresh for EVERY window, on the lookback period strictly
        # BEFORE this window starts - a model trained once on the whole
        # history and reused across all windows would leak future
        # information into earlier test windows.
        train_start = (datetime.strptime(win_start, "%Y-%m-%d")
                        - relativedelta(months=args.ml_train_months)).strftime("%Y-%m-%d")
        train_df = fetch_historical_range(args.symbol, args.timeframe, train_start, win_start)
        model, feature_cols = ml_classifier.train_model(train_df)
        if model is None:
            return None, "not enough clean training data for this window"
        signal_fn = ml_classifier.build_signal_fn(model, feature_cols)
        bt = Backtester(df, starting_balance=starting_balance,
                         add_indicators_fn=ml_classifier.add_indicators_for_backtest,
                         signal_fn=signal_fn, min_bars=210)
    else:
        spec = STRATEGIES[args.strategy]
        bt = Backtester(df, starting_balance=starting_balance,
                         add_indicators_fn=spec["add_indicators"],
                         signal_fn=spec["generate_signal"], min_bars=spec["min_bars"])

    return bt.run(), None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default="2025-06-01")
    parser.add_argument("--window-months", type=int, default=3)
    parser.add_argument("--strategy", default="legacy", choices=CHOICES,
                         help="Which strategy to walk-forward test: " + ", ".join(CHOICES))
    parser.add_argument("--ml-train-months", type=int, default=12,
                         help="For --strategy ml: months of trailing data used to retrain before each window")
    parser.add_argument("--no-trend-mode", action="store_true",
                         help="legacy strategy only: disable trend-following, isolate mean-reversion")
    args = parser.parse_args()

    if args.no_trend_mode:
        settings.USE_TREND_MODE = False
        print("Trend mode disabled - mean-reversion only.\n")

    windows = generate_windows(args.start, args.end, args.window_months)
    print(f"Running walk-forward validation ({args.strategy}): {len(windows)} windows "
          f"of ~{args.window_months} month(s) each\n")

    results = []
    for win_start, win_end in windows:
        print(f"Window {win_start} to {win_end}...")
        try:
            report, skip_reason = run_one_window(args, win_start, win_end)
            if skip_reason:
                print(f"  Skipped - {skip_reason}")
                continue
            results.append({
                "window": f"{win_start} to {win_end}",
                "strategy_pct": report["total_return_pct"],
                "buy_hold_pct": report["buy_hold_return_pct"],
                "beat_bh": report["beat_buy_hold"],
                "trades": report["total_trades"],
                "win_rate": report["win_rate_pct"],
            })
        except Exception as e:
            print(f"  Error: {e}")

    print("\n" + "=" * 90)
    print(f"{'Window':<25} {'Strategy %':<12} {'Buy&Hold %':<12} {'Beat B&H':<10} {'Trades':<8} {'Win %':<8}")
    print("=" * 90)
    for r in results:
        beat = "YES" if r["beat_bh"] else "no"
        print(f"{r['window']:<25} {r['strategy_pct']:<12} {r['buy_hold_pct']:<12} {beat:<10} {r['trades']:<8} {r['win_rate']:<8}")
    print("=" * 90)

    if results:
        wins = sum(1 for r in results if r["beat_bh"])
        avg_strategy = sum(r["strategy_pct"] for r in results) / len(results)
        avg_bh = sum(r["buy_hold_pct"] for r in results) / len(results)
        print(f"\nSummary: strategy beat buy-and-hold in {wins}/{len(results)} windows")
        print(f"Average strategy return per window: {avg_strategy:.2f}%")
        print(f"Average buy-and-hold return per window: {avg_bh:.2f}%")
        print("\nWhy this matters: if the strategy only wins in 1-2 cherry-picked")
        print("windows (like a single crash period) and loses in most others,")
        print("that's a sign of a narrow edge, not a reliable one.\n")


if __name__ == "__main__":
    main()
