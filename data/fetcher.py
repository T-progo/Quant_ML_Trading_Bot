"""
Handles fetching OHLCV (candlestick) data from Binance via ccxt.
Used by both the backtester (historical data) and the live bot (recent data).
"""
import ccxt
import pandas as pd
import time
from config import settings


def get_exchange():
    """Create a ccxt Binance exchange instance, pointed at testnet if configured.
    Used for account actions: balances, placing orders, live trading."""
    exchange = ccxt.binance({
        "apiKey": settings.BINANCE_API_KEY,
        "secret": settings.BINANCE_API_SECRET,
        "enableRateLimit": True,
        "timeout": 30000,  # 30 seconds (default is 10s) - helps on slower connections
    })
    if settings.USE_TESTNET:
        exchange.set_sandbox_mode(True)
    return exchange


def get_public_data_exchange():
    """
    Create a ccxt Binance instance pointed at the REAL exchange (not testnet),
    used only for reading public historical candle data.

    Why: Binance's testnet resets periodically and does not retain deep
    historical data, so it's unsuitable for backtesting. Historical OHLCV
    candles are public market data (no account/keys needed), so we can
    safely pull them from the real exchange purely for backtesting purposes
    without ever touching real funds or placing any orders here.
    """
    return ccxt.binance({
        "enableRateLimit": True,
        "timeout": 30000,
    })


def fetch_ohlcv(symbol=None, timeframe=None, limit=500, since=None):
    """
    Fetch OHLCV candles and return as a pandas DataFrame with columns:
    timestamp, open, high, low, close, volume
    """
    symbol = symbol or settings.SYMBOL
    timeframe = timeframe or settings.TIMEFRAME
    exchange = get_exchange()

    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit, since=since)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)
    return df


def fetch_historical_range(symbol, timeframe, start_date_str, end_date_str=None, max_retries=4):
    """
    Fetch a longer historical range by paginating through ccxt's fetch_ohlcv.
    Dates as 'YYYY-MM-DD'. Useful for backtesting over months of data.

    Uses the real Binance exchange (public data only, no keys needed) since
    testnet does not retain enough historical depth for backtesting.

    Retries each page a few times with backoff before giving up, since a
    single transient network timeout shouldn't throw away all the data
    already fetched from earlier pages.
    """
    exchange = get_public_data_exchange()
    since = exchange.parse8601(f"{start_date_str}T00:00:00Z")
    end_ts = exchange.parse8601(f"{end_date_str}T00:00:00Z") if end_date_str else exchange.milliseconds()

    all_candles = []
    while since < end_ts:
        candles = None
        last_error = None
        for attempt in range(max_retries):
            try:
                candles = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=1000)
                break
            except (ccxt.RequestTimeout, ccxt.NetworkError) as e:
                last_error = e
                wait = 2 ** attempt  # 1s, 2s, 4s, 8s
                print(f"  Network hiccup ({e.__class__.__name__}), retrying in {wait}s... "
                      f"(attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)

        if candles is None:
            print(f"  Giving up on this page after {max_retries} attempts. "
                  f"Returning {len(all_candles)} candles fetched so far.")
            if last_error:
                print(f"  Last error: {last_error}")
            break

        if not candles:
            break
        all_candles += candles
        since = candles[-1][0] + 1  # move past the last candle
        if len(candles) < 1000:
            break

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)
    df = df[df.index < pd.to_datetime(end_ts, unit="ms")] if end_date_str else df
    return df
