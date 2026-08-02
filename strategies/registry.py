"""
Maps a --strategy CLI name to its (add_indicators_fn, generate_signal_fn,
min_bars) triple, so run_backtest.py / run_walkforward.py can plug any of
them into Backtester without special-casing each one.

"ml" is NOT in here - it needs a model trained on data before the test
period (to avoid lookahead bias), so it's handled separately in the
scripts via strategies.ml_classifier.train_model() / build_signal_fn().
"legacy" is the original combined trend+mean-reversion strategy.
"""
from strategies import indicators as legacy
from strategies import breakout, volatility_squeeze, supertrend
from config import settings

STRATEGIES = {
    "legacy": {
        "add_indicators": legacy.add_indicators,
        "generate_signal": legacy.generate_signal,
        "min_bars": max(settings.SLOW_MA, settings.MACD_SLOW, settings.BB_PERIOD,
                         settings.TREND_MA, settings.ADX_PERIOD, settings.ATR_PERIOD) + 2,
        "description": "MA-cross + MACD + RSI trend mode, with an RSI/Bollinger mean-reversion mode for ranging markets",
    },
    "breakout": {
        "add_indicators": breakout.add_indicators,
        "generate_signal": breakout.generate_signal,
        "min_bars": max(breakout.DONCHIAN_PERIOD, breakout.VOLUME_MA_PERIOD,
                         settings.ADX_PERIOD, settings.ATR_PERIOD) + 2,
        "description": "Donchian-channel N-bar breakout with volume + ADX confirmation",
    },
    "volatility": {
        "add_indicators": volatility_squeeze.add_indicators,
        "generate_signal": volatility_squeeze.generate_signal,
        "min_bars": max(volatility_squeeze.BB_PERIOD, volatility_squeeze.SQUEEZE_LOOKBACK,
                         settings.ATR_PERIOD) + 2,
        "description": "Bollinger Band squeeze followed by a directional breakout",
    },
    "supertrend": {
        "add_indicators": supertrend.add_indicators,
        "generate_signal": supertrend.generate_signal,
        "min_bars": max(supertrend.SUPERTREND_PERIOD, settings.ATR_PERIOD) + 2,
        "description": "Single ATR-based Supertrend indicator, trades on direction flips",
    },
}

CHOICES = list(STRATEGIES.keys()) + ["ml"]
