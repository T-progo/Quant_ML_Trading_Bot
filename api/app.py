"""
Flask API for the trading bot. Exposes endpoints to:
- Check current price/signal
- View paper trading state (balance, position, trade log)
- Trigger a backtest
- Health check

Run with: python api/app.py
Then visit: http://localhost:5000/status
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, request
from data.fetcher import fetch_ohlcv, fetch_historical_range
from strategies.indicators import add_indicators, generate_signal
from backtest.backtester import Backtester
from execution.paper_trader import PaperTrader, STATE_FILE
from config import settings
import json

app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/signal", methods=["GET"])
def signal():
    """Get the current strategy signal for the configured symbol."""
    df = fetch_ohlcv(limit=200)
    df = add_indicators(df)
    sig, reason, mode = generate_signal(df)
    latest = df.iloc[-1]
    return jsonify({
        "symbol": settings.SYMBOL,
        "timeframe": settings.TIMEFRAME,
        "price": float(latest["close"]),
        "signal": sig,
        "mode": mode,
        "reason": reason,
        "indicators": {
            "ma_fast": float(latest["ma_fast"]) if latest["ma_fast"] == latest["ma_fast"] else None,
            "ma_slow": float(latest["ma_slow"]) if latest["ma_slow"] == latest["ma_slow"] else None,
            "rsi": float(latest["rsi"]) if latest["rsi"] == latest["rsi"] else None,
            "macd": float(latest["macd"]) if latest["macd"] == latest["macd"] else None,
        }
    })


@app.route("/paper/status", methods=["GET"])
def paper_status():
    """View current paper trading balance, open position, and trade history."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return jsonify(json.load(f))
    return jsonify({"balance": settings.PAPER_STARTING_BALANCE, "position": None, "trade_log": []})


@app.route("/paper/tick", methods=["POST"])
def paper_tick():
    """Manually trigger one paper-trading cycle (useful for testing without the loop running)."""
    trader = PaperTrader()
    trader.run_once()
    return jsonify({"status": "tick executed", "balance": trader.balance, "position": trader.position})


@app.route("/backtest", methods=["GET"])
def backtest():
    """
    Run a backtest. Query params: symbol, timeframe, start, end
    Example: /backtest?symbol=BTC/USDT&timeframe=15m&start=2025-01-01
    """
    symbol = request.args.get("symbol", settings.SYMBOL)
    timeframe = request.args.get("timeframe", settings.TIMEFRAME)
    start = request.args.get("start", "2025-01-01")
    end = request.args.get("end")

    df = fetch_historical_range(symbol, timeframe, start, end)
    if len(df) < 50:
        return jsonify({"error": "Not enough historical data for this range"}), 400

    bt = Backtester(df)
    report = bt.run()
    # Trim trade/equity detail for API response size
    report["trades"] = report["trades"][-50:]
    report["equity_curve"] = report["equity_curve"][-200:]
    return jsonify(report)


if __name__ == "__main__":
    app.run(host=settings.API_HOST, port=settings.API_PORT, debug=True)
