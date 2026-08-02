"""
Supertrend strategy: a single ATR-based trend-following indicator that
flips direction when price crosses its band. Included as a genuinely
different trend-following approach from the legacy MA-cross + MACD + RSI
combo - one indicator, one clean flip signal, instead of four indicators
that all have to agree at once (which was part of why the legacy trend
mode entered late).

Long-only (spot account): a flip to downtrend exits an existing long
early, it never opens a short.
"""
import pandas as pd
import pandas_ta_classic as ta
from config import settings

SUPERTREND_PERIOD = 10
SUPERTREND_MULTIPLIER = 3.0


def add_indicators(df):
    df = df.copy()
    st = ta.supertrend(df["high"], df["low"], df["close"],
                        length=SUPERTREND_PERIOD, multiplier=SUPERTREND_MULTIPLIER)
    # Columns are named like SUPERT_10_3.0 (the line) and SUPERTd_10_3.0
    # (direction: 1 = uptrend, -1 = downtrend) - match by prefix since the
    # exact suffix depends on the period/multiplier passed in.
    line_col = [c for c in st.columns if c.startswith("SUPERT_")][0]
    dir_col = [c for c in st.columns if c.startswith("SUPERTd_")][0]
    df["supertrend"] = st[line_col]
    df["supertrend_dir"] = st[dir_col]

    atr = ta.atr(df["high"], df["low"], df["close"], length=settings.ATR_PERIOD)
    df["atr"] = atr
    return df


def generate_signal(df):
    min_len = max(SUPERTREND_PERIOD, settings.ATR_PERIOD) + 2
    if len(df) < min_len:
        return "HOLD", "Not enough data yet", "supertrend"

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    if pd.isna(curr["supertrend_dir"]) or pd.isna(prev["supertrend_dir"]):
        return "HOLD", "Indicators still warming up", "supertrend"

    flipped_up = prev["supertrend_dir"] < 0 and curr["supertrend_dir"] > 0
    flipped_down = prev["supertrend_dir"] > 0 and curr["supertrend_dir"] < 0

    if flipped_up:
        reason = f"[SUPERTREND] Flipped to uptrend at {curr['supertrend']:.2f}"
        return "BUY", reason, "supertrend"

    if flipped_down:
        reason = f"[SUPERTREND] Flipped to downtrend at {curr['supertrend']:.2f}"
        return "SELL", reason, "supertrend"

    return "HOLD", "No new Supertrend flip", "supertrend"
