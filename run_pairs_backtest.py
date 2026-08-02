"""
Research-only backtest for the pairs/stat-arb strategy (see
strategies/pairs_stat_arb.py for why this can't run as live spot execution).

Usage:
    python run_pairs_backtest.py --symbol1 BTC/USDT --symbol2 ETH/USDT --timeframe 1h --start 2023-01-01 --end 2023-10-01
"""
import argparse
from data.fetcher import fetch_historical_range
from strategies.pairs_stat_arb import align_pair, PairsBacktester, print_report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol1", default="BTC/USDT")
    parser.add_argument("--symbol2", default="ETH/USDT")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--end", default=None)
    args = parser.parse_args()

    print(f"Fetching {args.symbol1} and {args.symbol2} ({args.timeframe}) from {args.start}...")
    df1 = fetch_historical_range(args.symbol1, args.timeframe, args.start, args.end)
    df2 = fetch_historical_range(args.symbol2, args.timeframe, args.start, args.end)
    print(f"Fetched {len(df1)} / {len(df2)} candles.")

    merged = align_pair(df1, df2)
    if len(merged) < 100:
        print("Not enough overlapping data. Try a wider date range.")
        return

    bt = PairsBacktester(merged, args.symbol1, args.symbol2)
    report = bt.run()
    print_report(report)


if __name__ == "__main__":
    main()
