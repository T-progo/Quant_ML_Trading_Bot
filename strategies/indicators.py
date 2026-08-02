"""
Technical indicator calculations and signal generation.
Uses pandas-ta-classic (the actively maintained fork of pandas-ta) for
indicator math, keeps signal logic explicit and readable.
"""
import pandas_ta_classic as ta
from config import settings


def add_indicators(df):
    """Add all indicator columns to the OHLCV dataframe. Returns a new dataframe."""
    df = df.copy()

    df["ma_fast"] = ta.sma(df["close"], length=settings.FAST_MA)
    df["ma_slow"] = ta.sma(df["close"], length=settings.SLOW_MA)
    df["ma_trend"] = ta.sma(df["close"], length=settings.TREND_MA)

    df["rsi"] = ta.rsi(df["close"], length=settings.RSI_PERIOD)

    macd = ta.macd(
        df["close"],
        fast=settings.MACD_FAST,
        slow=settings.MACD_SLOW,
        signal=settings.MACD_SIGNAL,
    )
    # Column naming can vary slightly across pandas-ta versions (trailing
    # suffix differences), so match by prefix instead of hardcoding the full name.
    macd_col = [c for c in macd.columns if c.startswith("MACD_")][0]
    signal_col = [c for c in macd.columns if c.startswith("MACDs_")][0]
    df["macd"] = macd[macd_col]
    df["macd_signal"] = macd[signal_col]

    bb = ta.bbands(df["close"], length=settings.BB_PERIOD, std=settings.BB_STD)
    bbl_col = [c for c in bb.columns if c.startswith("BBL_")][0]
    bbu_col = [c for c in bb.columns if c.startswith("BBU_")][0]
    df["bb_lower"] = bb[bbl_col]
    df["bb_upper"] = bb[bbu_col]

    adx = ta.adx(df["high"], df["low"], df["close"], length=settings.ADX_PERIOD)
    adx_col = [c for c in adx.columns if c.startswith("ADX_")][0]
    df["adx"] = adx[adx_col]

    atr = ta.atr(df["high"], df["low"], df["close"], length=settings.ATR_PERIOD)
    df["atr"] = atr

    return df


def generate_signal(df):
    """
    Combine indicators into a single BUY / SELL / HOLD signal for the latest candle.

    Two distinct modes, chosen by market condition (ADX = trend strength):

    TREND MODE (ADX >= ADX_MIN_STRENGTH, i.e. a real trend exists):
      BUY  when: price above 200-MA AND fast/slow MA bullish cross AND RSI healthy AND MACD bullish
      SELL when: price below 200-MA AND fast/slow MA bearish cross AND RSI healthy AND MACD bearish
      Exits: ATR-based stop-loss + trailing stop (see backtester).

    MEAN-REVERSION MODE (ADX < ADX_MIN_STRENGTH, i.e. ranging/choppy market):
      BUY  when: RSI is deeply oversold AND price at/below the lower Bollinger Band
      SELL when: RSI is deeply overbought AND price at/above the upper Bollinger Band
      Exits: fixed, tighter stop-loss/take-profit (MR_STOP_LOSS_PCT / MR_TAKE_PROFIT_PCT),
      since ranging moves are smaller than trending moves.

    Why two modes: the trend-following rules deliberately sit out during weak
    trends (that's what the ADX filter is for) - crypto spends a lot of its
    time ranging, so mean-reversion gives the bot something principled to do
    in that condition instead of just always holding.
    """
    if len(df) < max(settings.SLOW_MA, settings.MACD_SLOW, settings.BB_PERIOD, settings.TREND_MA, settings.ADX_PERIOD, settings.ATR_PERIOD) + 2:
        return "HOLD", "Not enough data yet", "trend"

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    strong_trend = curr["adx"] >= settings.ADX_MIN_STRENGTH

    if strong_trend and not settings.USE_TREND_MODE:
        return "HOLD", f"Trend mode disabled (ADX {curr['adx']:.1f})", "trend"

    if strong_trend:
        ma_cross_up = prev["ma_fast"] <= prev["ma_slow"] and curr["ma_fast"] > curr["ma_slow"]
        ma_cross_down = prev["ma_fast"] >= prev["ma_slow"] and curr["ma_fast"] < curr["ma_slow"]

        uptrend = curr["close"] > curr["ma_trend"]
        downtrend = curr["close"] < curr["ma_trend"]

        macd_bullish = curr["macd"] > curr["macd_signal"]
        macd_bearish = curr["macd"] < curr["macd_signal"]

        near_lower_band = curr["close"] <= curr["bb_lower"] * 1.01
        near_upper_band = curr["close"] >= curr["bb_upper"] * 0.99

        if ma_cross_up and uptrend and curr["rsi"] < settings.RSI_OVERBOUGHT and macd_bullish:
            reason = f"[TREND] Uptrend + MA bullish cross + MACD bullish + RSI healthy (ADX {curr['adx']:.1f})"
            if near_lower_band:
                reason += " + near lower Bollinger Band"
            return "BUY", reason, "trend"

        if ma_cross_down and downtrend and curr["rsi"] > settings.RSI_OVERSOLD and macd_bearish:
            reason = f"[TREND] Downtrend + MA bearish cross + MACD bearish + RSI healthy (ADX {curr['adx']:.1f})"
            if near_upper_band:
                reason += " + near upper Bollinger Band"
            return "SELL", reason, "trend"

        return "HOLD", "No trend-mode signal", "trend"

    # Weak trend -> ranging market -> mean-reversion mode
    if not settings.USE_MEAN_REVERSION:
        return "HOLD", f"Trend too weak (ADX {curr['adx']:.1f}) and mean-reversion disabled", "trend"

    oversold = curr["rsi"] <= settings.MR_RSI_OVERSOLD
    overbought = curr["rsi"] >= settings.MR_RSI_OVERBOUGHT
    at_lower_band = curr["close"] <= curr["bb_lower"]
    at_upper_band = curr["close"] >= curr["bb_upper"]

    if oversold and at_lower_band:
        reason = f"[MEAN-REVERSION] RSI deeply oversold ({curr['rsi']:.1f}) + at lower Bollinger Band (ADX {curr['adx']:.1f} - ranging market)"
        return "BUY", reason, "mean_reversion"

    if overbought and at_upper_band:
        reason = f"[MEAN-REVERSION] RSI deeply overbought ({curr['rsi']:.1f}) + at upper Bollinger Band (ADX {curr['adx']:.1f} - ranging market)"
        return "SELL", reason, "mean_reversion"

    return "HOLD", f"Ranging market (ADX {curr['adx']:.1f}) but no mean-reversion extreme yet", "mean_reversion"
