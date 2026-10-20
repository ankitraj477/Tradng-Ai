from datetime import time
import numpy as np
import pandas as pd

from .timing import IntradayTimingManager
from .vwap import calculate_session_vwap
from ..multitimeframe import MultiTimeframeAnalyzer
from ..pattern_strategies import BaseStrategy


class OpeningRangeBreakoutStrategy(BaseStrategy):
    """
    Intraday Opening Range Breakout (ORB) and Gap Strategy.
    1. Establishes the 15-minute Opening Range (09:15 - 09:30 IST).
    2. Requires volume confirmation (Time-of-day normalized RVOL >= min_rvol).
    3. Requires session VWAP alignment (Long > VWAP, Short < VWAP).
    4. Filters direction using macro daily bias (no long in downtrend, no short in uptrend).
    5. Fixed stop at ORB midpoint or ATR-based stop, with compulsory 15:10 square-off.
    """
    def __init__(self, orb_minutes=15, min_rvol=1.2, atr_stop_mult=1.5, target_mult=2.0):
        super().__init__("OpeningRangeBreakout", {
            "orb_minutes": orb_minutes,
            "min_rvol": min_rvol,
            "atr_stop_mult": atr_stop_mult,
            "target_mult": target_mult
        })
        self.orb_minutes = int(orb_minutes)
        self.min_rvol = float(min_rvol)
        self.atr_stop = float(atr_stop_mult)
        self.target_mult = float(target_mult)
        self.timing = IntradayTimingManager()

    def calculate_opening_range(self, intraday_df, current_date):
        """Extracts high, low, and mid of the 09:15 - 09:30 opening range for the date."""
        session_bars = intraday_df[intraday_df.index.date == current_date]
        if session_bars.empty:
            return None

        # Filter bars in 09:15 <= t < 09:30
        orb_bars = session_bars.between_time("09:15", "09:29")
        if orb_bars.empty:
            return None

        orb_h = float(orb_bars["High"].max())
        orb_l = float(orb_bars["Low"].min())
        orb_mid = (orb_h + orb_l) / 2.0
        return {
            "high": orb_h,
            "low": orb_l,
            "mid": orb_mid,
            "open": float(orb_bars["Open"].iloc[0]),
            "range": orb_h - orb_l
        }

    def decide(self, symbol, intraday_df, daily_df=None):
        if intraday_df is None or intraday_df.empty:
            return None

        current_bar = intraday_df.iloc[-1]
        current_time = intraday_df.index[-1]

        # 1. Timing Gate: must be in active trading window (09:30 - 14:45 IST)
        if not self.timing.can_enter(current_time):
            return None

        current_date = current_time.date()
        orb = self.calculate_opening_range(intraday_df, current_date)
        if orb is None or orb["range"] <= 0:
            return None

        # 2. Multi-timeframe daily bias filter
        daily_bias = "NEUTRAL"
        if daily_df is not None and len(daily_df) >= 50:
            analysis = MultiTimeframeAnalyzer.daily_direction(daily_df)
            daily_bias = analysis.get("bias", "NEUTRAL")

        # 3. Session VWAP
        vwap_df = calculate_session_vwap(intraday_df)
        if vwap_df.empty:
            return None
        current_vwap = float(vwap_df["vwap"].iloc[-1])

        # 4. Time-of-day normalized volume
        norm_vol = MultiTimeframeAnalyzer.normalize_tod_volume(intraday_df)
        rvol = float(norm_vol.iloc[-1]) if not norm_vol.empty else 1.0

        if rvol < self.min_rvol:
            return None  # Insufficient volume confirmation

        last_px = float(current_bar["Close"])
        # ATR calculation on intraday bars
        h, l, c = intraday_df["High"], intraday_df["Low"], intraday_df["Close"]
        tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        atr = float(tr.tail(14).mean()) if len(tr) >= 14 else float(last_px * 0.005)

        # 5. Signal Evaluation
        # Bullish Breakout
        if last_px > orb["high"] and last_px > current_vwap and daily_bias != "BEARISH":
            stop_px = max(orb["mid"], last_px - (self.atr_stop * atr))
            risk = last_px - stop_px
            if risk <= 0: risk = last_px * 0.005
            target_px = last_px + (self.target_mult * risk)
            return {
                "symbol": symbol,
                "action": "BUY",
                "side": "LONG",
                "price": last_px,
                "stop_loss": round(stop_px, 2),
                "target": round(target_px, 2),
                "atr": round(atr, 2),
                "vwap": round(current_vwap, 2),
                "orb_high": round(orb["high"], 2),
                "rvol": round(rvol, 2),
                "strategy": self.name,
                "reason": f"ORB breakout above {orb['high']:.2f} with {rvol:.1f}x RVOL & VWAP support"
            }

        # Bearish Breakdown
        elif last_px < orb["low"] and last_px < current_vwap and daily_bias != "BULLISH":
            stop_px = min(orb["mid"], last_px + (self.atr_stop * atr))
            risk = stop_px - last_px
            if risk <= 0: risk = last_px * 0.005
            target_px = last_px - (self.target_mult * risk)
            return {
                "symbol": symbol,
                "action": "SHORT",
                "side": "SHORT",
                "price": last_px,
                "stop_loss": round(stop_px, 2),
                "target": round(target_px, 2),
                "atr": round(atr, 2),
                "vwap": round(current_vwap, 2),
                "orb_low": round(orb["low"], 2),
                "rvol": round(rvol, 2),
                "strategy": self.name,
                "reason": f"ORB breakdown below {orb['low']:.2f} with {rvol:.1f}x RVOL & VWAP resistance"
            }

        return None


    generate_signal = decide


ORBStrategy = OpeningRangeBreakoutStrategy


class ORBDeskStrategy:
    """Wrapper that adapts OpeningRangeBreakoutStrategy to live/paper desk evaluation."""
    def __init__(self, provider, cfg=None):
        self.provider = provider
        self.cfg = cfg or {}
        self.strategy = OpeningRangeBreakoutStrategy()

    def evaluate(self, symbol):
        try:
            intraday_df = self.provider.history(symbol, period="5d", interval="5m")
            daily_df = self.provider.history(symbol, period="60d", interval="1d")
            sig = self.strategy.decide(symbol, intraday_df, daily_df)
            if sig:
                from types import SimpleNamespace
                return SimpleNamespace(**sig)
        except Exception:
            pass
        return None

