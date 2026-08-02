"""
Runs the backtest across multiple symbol/timeframe combinations and prints
a comparison table. Useful for checking if a strategy is overfit to one
specific pair/timeframe, or if it holds up more broadly.

Usage:
    python run_comparison.py
    python run_comparison.py --start 2024-01-01 --end 2025-06-01
"""
import argparse
from data.fetcher import fetch_historical_range
from backtest.backtester import Backtester
from strategies.registry import STRATEGIES, CHOICES


COMBINATIONS = [
    ("BTC/USDT", "1h"),
    ("BTC/USDT", "4h"),
    ("ETH/USDT", "1h"),
    ("ETH/USDT", "4h"),
    ("SOL/USDT", "1h"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--strategy", default="legacy", choices=list(STRATEGIES.keys()),
                         help="Which strategy to compare across symbols (ml isn't supported here - "
                              "it needs its own training run per symbol, see run_backtest.py --strategy ml)")
    args = parser.parse_args()

    spec = STRATEGIES[args.strategy]
    results = []

    for symbol, timeframe in COMBINATIONS:
        print(f"Testing {symbol} ({timeframe})...")
        try:
            df = fetch_historical_range(symbol, timeframe, args.start, args.end)
            if len(df) < 250:
                print(f"  Skipped - not enough data ({len(df)} candles)")
                continue

            bt = Backtester(df, add_indicators_fn=spec["add_indicators"],
                             signal_fn=spec["generate_signal"], min_bars=spec["min_bars"])
            report = bt.run()
            results.append({
                "symbol": symbol,
                "timeframe": timeframe,
                "return_pct": report["total_return_pct"],
                "buy_hold_pct": report["buy_hold_return_pct"],
                "beat_buy_hold": report["beat_buy_hold"],
                "trades": report["total_trades"],
                "win_rate": report["win_rate_pct"],
                "fees": report["total_fees_paid"],
            })
        except Exception as e:
            print(f"  Error: {e}")

    print("\n" + "=" * 95)
    print(f"{'Symbol':<10} {'TF':<5} {'Strategy %':<12} {'Buy&Hold %':<12} {'Beat B&H':<10} {'Trades':<8} {'Win %':<8} {'Fees $':<8}")
    print("=" * 95)
    for r in results:
        beat = "YES" if r["beat_buy_hold"] else "no"
        print(f"{r['symbol']:<10} {r['timeframe']:<5} {r['return_pct']:<12} {r['buy_hold_pct']:<12} {beat:<10} {r['trades']:<8} {r['win_rate']:<8} {r['fees']:<8}")
    print("=" * 95 + "\n")


if __name__ == "__main__":
    main()
