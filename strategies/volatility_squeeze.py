"""
Volatility-squeeze strategy: Bollinger Bands contract tightly during low-
volatility consolidation ("the squeeze"), and big moves tend to start right
after the bands start expanding again. Idea: wait for a squeeze, then trade
the direction of the breakout once volatility actually expands - instead of
trend-mode's MA cross (lagging) or mean-reversion's fade-the-extreme
(fights the move).

Long-only (spot account): a downside breakout after a squeeze exits an
existing long early, it never opens a short.
"""
import pandas as pd
import pandas_ta_classic as ta
from config import settings

BB_PERIOD = 20
BB_STD = 2
SQUEEZE_LOOKBACK = 120     # bars of BB-width history used to judge "tight" vs "normal"
SQUEEZE_PERCENTILE = 0.20  # squeeze = current width in the bottom 20% of recent widths
BREAKOUT_LOOKBACK = 6      # a squeeze must have occurred within this many bars to still count


def add_indicators(df):
    df = df.copy()
    bb = ta.bbands(df["close"], length=BB_PERIOD, std=BB_STD)
    bbl_col = [c for c in bb.columns if c.startswith("BBL_")][0]
    bbu_col = [c for c in bb.columns if c.startswith("BBU_")][0]
    bbm_col = [c for c in bb.columns if c.startswith("BBM_")][0]
    df["bb_lower"] = bb[bbl_col]
    df["bb_upper"] = bb[bbu_col]
    df["bb_mid"] = bb[bbm_col]
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]

    # Rolling percentile rank of today's width vs recent history - a direct
    # measure of "how tight is this compared to what's normal lately".
    df["bb_width_pct_rank"] = df["bb_width"].rolling(SQUEEZE_LOOKBACK).apply(
        lambda w: (w < w.iloc[-1]).mean(), raw=False
    )

    atr = ta.atr(df["high"], df["low"], df["close"], length=settings.ATR_PERIOD)
    df["atr"] = atr
    return df


def generate_signal(df):
    min_len = max(BB_PERIOD, SQUEEZE_LOOKBACK, settings.ATR_PERIOD) + 2
    if len(df) < min_len:
        return "HOLD", "Not enough data yet", "volatility_squeeze"

    window = df.iloc[-(BREAKOUT_LOOKBACK + 1):]
    curr = df.iloc[-1]

    if pd.isna(curr["bb_width_pct_rank"]) or pd.isna(curr["bb_upper"]):
        return "HOLD", "Indicators still warming up", "volatility_squeeze"

    had_recent_squeeze = (window["bb_width_pct_rank"].iloc[:-1] <= SQUEEZE_PERCENTILE).any()

    if not had_recent_squeeze:
        return "HOLD", "No recent volatility squeeze", "volatility_squeeze"

    broke_upper = curr["close"] > curr["bb_upper"]
    broke_lower = curr["close"] < curr["bb_lower"]

    if broke_upper:
        reason = (f"[VOL-SQUEEZE] Broke upper band after a squeeze "
                  f"(width percentile {curr['bb_width_pct_rank']*100:.0f}%)")
        return "BUY", reason, "volatility_squeeze"

    if broke_lower:
        reason = "[VOL-SQUEEZE] Broke lower band after a squeeze - downside expansion"
        return "SELL", reason, "volatility_squeeze"

    return "HOLD", "Squeezed recently but no breakout yet", "volatility_squeeze"
