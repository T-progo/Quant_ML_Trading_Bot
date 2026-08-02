"""
Breakout / momentum strategy: trades new N-bar highs (Donchian channel
breakout) instead of a moving-average cross. Idea: don't wait for a lagging
MA to confirm a trend - enter as soon as price makes a fresh high with
volume and trend-strength confirmation, which is closer to how momentum
actually gets traded (turtle-style breakout systems).

Long-only (spot account): a breakdown below the lower channel exits an
existing long early, it never opens a short.
"""
import pandas as pd
import pandas_ta_classic as ta
from config import settings

DONCHIAN_PERIOD = 20      # N-bar high/low channel
VOLUME_MA_PERIOD = 20     # rolling average volume, for a conviction filter
VOLUME_MULT = 1.2         # breakout volume must be at least this x the rolling average
ADX_MIN_STRENGTH = 20     # only take breakouts when the broader trend has some strength


def add_indicators(df):
    df = df.copy()
    # Shift(1) so the channel is the highest/lowest of the PRIOR N bars,
    # not including the current bar - otherwise every bar trivially
    # "breaks out" of a channel that includes itself.
    df["donchian_high"] = df["high"].shift(1).rolling(DONCHIAN_PERIOD).max()
    df["donchian_low"] = df["low"].shift(1).rolling(DONCHIAN_PERIOD).min()
    df["volume_ma"] = df["volume"].rolling(VOLUME_MA_PERIOD).mean()

    adx = ta.adx(df["high"], df["low"], df["close"], length=settings.ADX_PERIOD)
    adx_col = [c for c in adx.columns if c.startswith("ADX_")][0]
    df["adx"] = adx[adx_col]

    atr = ta.atr(df["high"], df["low"], df["close"], length=settings.ATR_PERIOD)
    df["atr"] = atr
    return df


def generate_signal(df):
    min_len = max(DONCHIAN_PERIOD, VOLUME_MA_PERIOD, settings.ADX_PERIOD, settings.ATR_PERIOD) + 2
    if len(df) < min_len:
        return "HOLD", "Not enough data yet", "breakout"

    curr = df.iloc[-1]

    if any(pd.isna(curr[c]) for c in ("donchian_high", "donchian_low", "volume_ma", "adx")):
        return "HOLD", "Indicators still warming up", "breakout"

    strong_enough = curr["adx"] >= ADX_MIN_STRENGTH
    volume_confirmed = curr["volume"] >= curr["volume_ma"] * VOLUME_MULT

    broke_high = curr["close"] > curr["donchian_high"]
    broke_low = curr["close"] < curr["donchian_low"]

    if broke_high and strong_enough and volume_confirmed:
        reason = (f"[BREAKOUT] New {DONCHIAN_PERIOD}-bar high on {curr['volume']/curr['volume_ma']:.1f}x "
                   f"average volume (ADX {curr['adx']:.1f})")
        return "BUY", reason, "breakout"

    if broke_low:
        reason = f"[BREAKOUT] Broke {DONCHIAN_PERIOD}-bar low - momentum reversing"
        return "SELL", reason, "breakout"

    return "HOLD", "No fresh breakout", "breakout"
