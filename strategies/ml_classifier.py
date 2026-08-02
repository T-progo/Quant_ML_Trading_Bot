"""
ML classifier strategy: trains a gradient-boosted classifier on engineered
technical features to predict whether price will be meaningfully higher
N bars from now, and trades on the model's predicted probability.

IMPORTANT - this is NOT a plug-and-play "add_indicators/generate_signal"
strategy like the others, because it needs a model trained on data that
comes strictly BEFORE whatever it's being tested on (otherwise the
backtest is lookahead-biased and the results are meaningless). Use
train_model() on a training slice, then build_signal_fn() to get a
signal_fn closure bound to that trained model, and pass both the
resulting add_indicators/signal_fn pair into Backtester manually.
See run_backtest.py / run_walkforward.py --strategy ml for the reference
usage (retrains fresh per walk-forward window on the data preceding it).
"""
import numpy as np
import pandas as pd
import pandas_ta_classic as ta
from config import settings

LABEL_HORIZON_BARS = 8      # how many bars ahead we're predicting
LABEL_MOVE_THRESHOLD = 0.004  # must move at least this much (0.4%) to count as "up"
BUY_PROB_THRESHOLD = 0.58    # only buy when the model is fairly confident
SELL_PROB_THRESHOLD = 0.42   # exit an existing long if confidence in "up" drops below this

FEATURE_COLUMNS = [
    "ret_1", "ret_3", "ret_8", "ret_20",
    "rsi", "macd_hist", "bb_pctb", "adx", "atr_pct",
    "volume_z", "dist_from_ma50", "dist_from_ma200",
]


def build_features(df):
    """Add engineered feature columns (causal - only ever looks backward)."""
    df = df.copy()

    df["ret_1"] = df["close"].pct_change(1)
    df["ret_3"] = df["close"].pct_change(3)
    df["ret_8"] = df["close"].pct_change(8)
    df["ret_20"] = df["close"].pct_change(20)

    df["rsi"] = ta.rsi(df["close"], length=14)

    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    hist_col = [c for c in macd.columns if c.startswith("MACDh_")][0]
    df["macd_hist"] = macd[hist_col]

    bb = ta.bbands(df["close"], length=20, std=2)
    bbl_col = [c for c in bb.columns if c.startswith("BBL_")][0]
    bbu_col = [c for c in bb.columns if c.startswith("BBU_")][0]
    band_range = (bb[bbu_col] - bb[bbl_col]).replace(0, np.nan)
    df["bb_pctb"] = (df["close"] - bb[bbl_col]) / band_range

    adx = ta.adx(df["high"], df["low"], df["close"], length=14)
    adx_col = [c for c in adx.columns if c.startswith("ADX_")][0]
    df["adx"] = adx[adx_col]

    atr = ta.atr(df["high"], df["low"], df["close"], length=14)
    df["atr"] = atr
    df["atr_pct"] = atr / df["close"]

    vol_mean = df["volume"].rolling(20).mean()
    vol_std = df["volume"].rolling(20).std().replace(0, np.nan)
    df["volume_z"] = (df["volume"] - vol_mean) / vol_std

    ma50 = df["close"].rolling(50).mean()
    ma200 = df["close"].rolling(200).mean()
    df["dist_from_ma50"] = (df["close"] - ma50) / ma50
    df["dist_from_ma200"] = (df["close"] - ma200) / ma200

    return df


def build_labels(df):
    """1 = price is up by at least LABEL_MOVE_THRESHOLD, N bars from now. 0 otherwise.
    Uses future data ON PURPOSE (that's the label) - only ever call this on
    TRAINING data, never on the data actually being backtested/traded."""
    df = df.copy()
    future_return = df["close"].shift(-LABEL_HORIZON_BARS) / df["close"] - 1
    df["label"] = (future_return >= LABEL_MOVE_THRESHOLD).astype(int)
    return df


def train_model(train_df):
    """Train a classifier on a slice of historical data. Returns (model, feature_cols),
    or (None, None) if there isn't enough clean data to train on."""
    from sklearn.ensemble import GradientBoostingClassifier

    df = build_features(train_df)
    df = build_labels(df)
    df = df.dropna(subset=FEATURE_COLUMNS + ["label"])

    if len(df) < 200:
        return None, None

    X = df[FEATURE_COLUMNS].values
    y = df["label"].values

    if len(np.unique(y)) < 2:
        # All one class (e.g. a training window that's pure uptrend) -
        # nothing meaningful to learn, refuse to train a degenerate model.
        return None, None

    model = GradientBoostingClassifier(
        n_estimators=150, max_depth=3, learning_rate=0.05, subsample=0.8, random_state=42,
    )
    model.fit(X, y)
    return model, FEATURE_COLUMNS


def build_signal_fn(model, feature_cols):
    """Wrap a trained model into a (signal, reason, mode) function matching
    the same contract as the other strategies' generate_signal, so it can be
    dropped straight into Backtester as signal_fn."""

    def signal_fn(window_df):
        min_len = 210  # enough for the 200-bar MA feature to warm up
        if len(window_df) < min_len:
            return "HOLD", "Not enough data yet", "ml"

        curr = window_df.iloc[-1]
        if any(pd.isna(curr.get(c)) for c in feature_cols):
            return "HOLD", "Features still warming up", "ml"

        X = curr[feature_cols].values.reshape(1, -1)
        prob_up = model.predict_proba(X)[0][1]

        if prob_up >= BUY_PROB_THRESHOLD:
            return "BUY", f"[ML] Model predicts up-move (p={prob_up:.2f})", "ml"
        if prob_up <= SELL_PROB_THRESHOLD:
            return "SELL", f"[ML] Model confidence in up-move dropped (p={prob_up:.2f})", "ml"
        return "HOLD", f"[ML] No strong signal (p={prob_up:.2f})", "ml"

    return signal_fn


def add_indicators_for_backtest(df):
    """The add_indicators_fn Backtester needs - just the feature columns,
    no label (labels only exist during training, never during a live/backtest
    run since they require future data that wouldn't exist yet)."""
    return build_features(df)
