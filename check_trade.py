"""
On-demand trade check. Run this any time to ask: "should I trade right now?"

It fetches the latest market data, runs the strategy, and if there's a
BUY or SELL signal, tells you exactly:
  - Entry price
  - Stop-loss price
  - Take-profit price
  - Position size (based on your TRADE_AMOUNT_USDT setting)
  - WHY the signal fired (which indicators agreed)

If there's no signal, it tells you why not (e.g. "no MA crossover" or
"against the trend"), so you understand what the bot is waiting for.

Usage:
    python check_trade.py
    python check_trade.py --symbol ETH/USDT --timeframe 1h
"""
import argparse
from data.fetcher import fetch_ohlcv
from strategies.indicators import add_indicators, generate_signal
from config import settings


def explain_trade(symbol=None, timeframe=None):
    symbol = symbol or settings.SYMBOL
    timeframe = timeframe or settings.TIMEFRAME

    df = fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=250)
    df = add_indicators(df)
    signal, reason, mode = generate_signal(df)
    latest = df.iloc[-1]
    price = float(latest["close"])

    print("\n" + "=" * 55)
    print(f"TRADE CHECK — {symbol} ({timeframe})")
    print("=" * 55)
    print(f"Current price:   {price:.4f}")
    print(f"RSI:             {latest['rsi']:.2f}")
    print(f"Trend (200 MA):  {'above (uptrend)' if price > latest['ma_trend'] else 'below (downtrend)'}")
    print(f"ADX (trend str): {latest['adx']:.1f}  ->  {'TREND mode' if mode == 'trend' else 'RANGING - mean-reversion mode'}")
    print("-" * 55)

    if signal == "HOLD":
        print("Signal: HOLD — no trade right now")
        print(f"Why not: {reason}")
        print("=" * 55 + "\n")
        return

    amount = settings.TRADE_AMOUNT_USDT / price

    if mode == "mean_reversion":
        sl_pct = settings.MR_STOP_LOSS_PCT
        tp_pct = settings.MR_TAKE_PROFIT_PCT
    elif settings.USE_ATR_STOPS and latest.get("atr") and latest["atr"] > 0:
        sl_pct = (latest["atr"] * settings.ATR_STOP_MULT) / price
        tp_pct = (latest["atr"] * settings.ATR_TRAIL_MULT) / price  # trailing distance, shown as reference
    else:
        sl_pct = settings.STOP_LOSS_PCT
        tp_pct = settings.TAKE_PROFIT_PCT

    if signal == "BUY":
        stop_loss = price * (1 - sl_pct)
        take_profit = price * (1 + tp_pct)
        print("Signal: BUY (open a long)")
        print(f"Why: {reason}")
        print("-" * 55)
        print(f"Entry price:      {price:.4f}")
        print(f"Stop-loss:        {stop_loss:.4f}  ({sl_pct*100:.2f}% risk)")
        if mode == "trend" and settings.USE_TRAILING_STOP:
            print(f"Trailing stop:    activates after {sl_pct*100:.2f}% profit, then trails by {tp_pct*100:.2f}%")
        else:
            print(f"Take-profit:      {take_profit:.4f}  ({tp_pct*100:.2f}% target)")
        print(f"Position size:    {amount:.6f} {symbol.split('/')[0]}  (${settings.TRADE_AMOUNT_USDT} notional)")
    else:  # SELL
        # This is a spot account - there is no short-selling. A SELL signal
        # only matters if the bot is already holding a long (it exits early);
        # with no open position there is nothing to sell and nothing to short.
        print("Signal: SELL (bearish - exits an existing long early; does NOT open a short)")
        print(f"Why: {reason}")

    print("=" * 55)
    print("Note: this is informational only. It does NOT place an order.")
    print("To have the bot auto-execute trades like this on your testnet")
    print("account continuously, run: python execution/testnet_trader.py")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--timeframe", default=None)
    args = parser.parse_args()
    explain_trade(args.symbol, args.timeframe)
