"""
Run this to backtest the strategy on historical data.

Usage:
    python run_backtest.py
    python run_backtest.py --start 2025-01-01 --end 2025-06-01 --symbol BTC/USDT --timeframe 15m
    python run_backtest.py --strategy breakout --start 2023-01-01 --end 2023-10-01
    python run_backtest.py --strategy ml --start 2023-01-01 --end 2023-10-01 --ml-train-months 12
"""
import argparse
from datetime import datetime
from dateutil.relativedelta import relativedelta
from data.fetcher import fetch_historical_range
from backtest.backtester import Backtester, print_report
from strategies.registry import STRATEGIES, CHOICES
from strategies import ml_classifier
from config import settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=settings.SYMBOL)
    parser.add_argument("--timeframe", default=settings.TIMEFRAME)
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--strategy", default="legacy", choices=CHOICES,
                         help="Which strategy to backtest: " + ", ".join(CHOICES))
    parser.add_argument("--ml-train-months", type=int, default=12,
                         help="For --strategy ml: months of data BEFORE --start used to train the model")
    parser.add_argument("--no-trend-mode", action="store_true",
                         help="legacy strategy only: disable trend-following, isolate mean-reversion")
    args = parser.parse_args()

    if args.no_trend_mode:
        settings.USE_TREND_MODE = False
        print("Trend mode disabled - mean-reversion only.")

    print(f"Fetching historical data for {args.symbol} ({args.timeframe}) from {args.start}...")
    df = fetch_historical_range(args.symbol, args.timeframe, args.start, args.end)
    print(f"Fetched {len(df)} candles.")

    if len(df) < 50:
        print("Not enough data returned. Try a wider date range or different timeframe.")
        return

    if args.strategy == "ml":
        train_start = (datetime.strptime(args.start, "%Y-%m-%d")
                        - relativedelta(months=args.ml_train_months)).strftime("%Y-%m-%d")
        print(f"Training ML model on {args.symbol} data from {train_start} to {args.start} "
              f"(never overlaps with the test period below)...")
        train_df = fetch_historical_range(args.symbol, args.timeframe, train_start, args.start)
        model, feature_cols = ml_classifier.train_model(train_df)
        if model is None:
            print("Not enough clean training data (or only one class present) - try a wider --ml-train-months.")
            return
        signal_fn = ml_classifier.build_signal_fn(model, feature_cols)
        bt = Backtester(df, add_indicators_fn=ml_classifier.add_indicators_for_backtest,
                         signal_fn=signal_fn, min_bars=210)
    else:
        spec = STRATEGIES[args.strategy]
        bt = Backtester(df, add_indicators_fn=spec["add_indicators"],
                         signal_fn=spec["generate_signal"], min_bars=spec["min_bars"])

    report = bt.run()
    print_report(report)


if __name__ == "__main__":
    main()
