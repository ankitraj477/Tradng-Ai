import numpy as np
import pandas as pd


class BaseStrategy:
    def __init__(self, name, params=None):
        self.name = name
        self.params = params or {}

    def decide(self, symbol, df):
        raise NotImplementedError


class BreakoutStrategy(BaseStrategy):
    """
    N-day Donchian Breakout with Volume Confirmation.
    Buys when price breaks above N-day high with above-average volume.
    Shorts when price breaks below N-day low with above-average volume.
    """
    def __init__(self, n_bars=20, volume_mult=1.5, atr_stop_mult=1.5, atr_target_mult=3.0):
        super().__init__("Breakout", {
            "n_bars": n_bars, "volume_mult": volume_mult,
            "atr_stop_mult": atr_stop_mult, "atr_target_mult": atr_target_mult
        })
        self.n_bars = int(n_bars)
        self.vol_mult = float(volume_mult)
        self.atr_stop = float(atr_stop_mult)
        self.atr_target = float(atr_target_mult)

    def decide(self, symbol, df):
        if df is None or len(df) <= self.n_bars + 1: return None
        c = df["Close"]
        h = df["High"]
        l = df["Low"]
        v = df["Volume"]

        # Shift by 1 to strictly prevent looking ahead at current bar
        prior_high = float(h.iloc[:-1].tail(self.n_bars).max())
        prior_low = float(l.iloc[:-1].tail(self.n_bars).min())
        avg_vol = float(v.iloc[:-1].tail(20).mean()) if len(v) > 20 else float(v.iloc[:-1].mean())

        last_px = float(c.iloc[-1])
        last_vol = float(v.iloc[-1])

        # ATR calculation
        tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        atr = float(tr.tail(14).mean()) if len(tr) >= 14 else float(last_px * 0.015)
        risk = max(atr * self.atr_stop, last_px * 0.005)

        if last_px > prior_high and last_vol >= avg_vol * self.vol_mult:
            return {
                "symbol": symbol, "action": "BUY", "side": "LONG", "price": last_px,
                "stop_loss": round(last_px - risk, 2), "target": round(last_px + self.atr_target * atr, 2),
                "atr": atr, "confidence": 80.0, "strategy": self.name,
                "reason": f"{self.n_bars}-bar breakout above {prior_high:.2f} with {last_vol/max(1, avg_vol):.1f}x volume"
            }
        elif last_px < prior_low and last_vol >= avg_vol * self.vol_mult:
            return {
                "symbol": symbol, "action": "SHORT", "side": "SHORT", "price": last_px,
                "stop_loss": round(last_px + risk, 2), "target": round(last_px - self.atr_target * atr, 2),
                "atr": atr, "confidence": 80.0, "strategy": self.name,
                "reason": f"{self.n_bars}-bar breakdown below {prior_low:.2f} with {last_vol/max(1, avg_vol):.1f}x volume"
            }
        return None


class EmaPullbackStrategy(BaseStrategy):
    """
    Trend Pullback Strategy.
    Enters in the direction of the dominant EMA trend when price pulls back to test EMA20/50.
    """
    def __init__(self, fast_ema=20, slow_ema=50, atr_stop_mult=1.5, atr_target_mult=2.5):
        super().__init__("EmaPullback", {
            "fast_ema": fast_ema, "slow_ema": slow_ema,
            "atr_stop_mult": atr_stop_mult, "atr_target_mult": atr_target_mult
        })
        self.fast = int(fast_ema)
        self.slow = int(slow_ema)
        self.atr_stop = float(atr_stop_mult)
        self.atr_target = float(atr_target_mult)

    def decide(self, symbol, df):
        if df is None or len(df) <= self.slow + 5: return None
        c = df["Close"]
        h = df["High"]
        l = df["Low"]

        ema_fast = c.ewm(span=self.fast, adjust=False).mean()
        ema_slow = c.ewm(span=self.slow, adjust=False).mean()

        fast_val = float(ema_fast.iloc[-1])
        slow_val = float(ema_slow.iloc[-1])
        last_px = float(c.iloc[-1])
        low_px = float(l.iloc[-1])
        high_px = float(h.iloc[-1])

        tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        atr = float(tr.tail(14).mean()) if len(tr) >= 14 else float(last_px * 0.015)
        risk = max(atr * self.atr_stop, last_px * 0.005)

        # Bullish Pullback: Uptrend (Fast > Slow), price touched or tested Fast EMA and closed above it
        if fast_val > slow_val and low_px <= fast_val * 1.002 and last_px > fast_val:
            return {
                "symbol": symbol, "action": "BUY", "side": "LONG", "price": last_px,
                "stop_loss": round(last_px - risk, 2), "target": round(last_px + self.atr_target * atr, 2),
                "atr": atr, "confidence": 75.0, "strategy": self.name,
                "reason": f"Pullback bounce off {self.fast}-EMA in uptrend"
            }
        # Bearish Pullback: Downtrend (Fast < Slow), price touched Fast EMA and rejected below it
        elif fast_val < slow_val and high_px >= fast_val * 0.998 and last_px < fast_val:
            return {
                "symbol": symbol, "action": "SHORT", "side": "SHORT", "price": last_px,
                "stop_loss": round(last_px + risk, 2), "target": round(last_px - self.atr_target * atr, 2),
                "atr": atr, "confidence": 75.0, "strategy": self.name,
                "reason": f"Pullback rejection at {self.fast}-EMA in downtrend"
            }
        return None


class RsiMeanReversionStrategy(BaseStrategy):
    """
    RSI-2 Mean Reversion Strategy (Larry Connors style).
    Buys severe short-term oversold dips within long-term uptrends (Close > 200 EMA).
    """
    def __init__(self, rsi_period=2, oversold=10.0, overbought=90.0, trend_span=100, atr_stop_mult=2.0):
        super().__init__("RsiMeanReversion", {
            "rsi_period": rsi_period, "oversold": oversold,
            "overbought": overbought, "trend_span": trend_span, "atr_stop_mult": atr_stop_mult
        })
        self.rsi_period = int(rsi_period)
        self.oversold = float(oversold)
        self.overbought = float(overbought)
        self.trend_span = int(trend_span)
        self.atr_stop = float(atr_stop_mult)

    def decide(self, symbol, df):
        if df is None or len(df) <= self.trend_span + 5: return None
        c = df["Close"]
        h = df["High"]
        l = df["Low"]

        # 2-period RSI calculation
        delta = c.diff()
        gain = delta.clip(lower=0).rolling(self.rsi_period).mean()
        loss = (-delta.clip(upper=0)).rolling(self.rsi_period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1])

        trend_ema = float(c.ewm(span=self.trend_span, adjust=False).mean().iloc[-1])
        last_px = float(c.iloc[-1])

        tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        atr = float(tr.tail(14).mean()) if len(tr) >= 14 else float(last_px * 0.015)
        risk = max(atr * self.atr_stop, last_px * 0.005)

        # Long: In macro uptrend, short-term extreme oversold
        if last_px > trend_ema and rsi_val < self.oversold:
            return {
                "symbol": symbol, "action": "BUY", "side": "LONG", "price": last_px,
                "stop_loss": round(last_px - risk, 2), "target": round(last_px + 2.0 * atr, 2),
                "atr": atr, "confidence": 85.0, "strategy": self.name,
                "reason": f"RSI-{self.rsi_period} oversold ({rsi_val:.1f}) in macro uptrend"
            }
        # Short: In macro downtrend, short-term extreme overbought
        elif last_px < trend_ema and rsi_val > self.overbought:
            return {
                "symbol": symbol, "action": "SHORT", "side": "SHORT", "price": last_px,
                "stop_loss": round(last_px + risk, 2), "target": round(last_px - 2.0 * atr, 2),
                "atr": atr, "confidence": 85.0, "strategy": self.name,
                "reason": f"RSI-{self.rsi_period} overbought ({rsi_val:.1f}) in macro downtrend"
            }
        return None


class RelativeStrengthMomentumStrategy(BaseStrategy):
    """
    Relative Strength Momentum Strategy.
    Goes long top decile leadership stocks outperforming the benchmark over 20/60 days.
    """
    def __init__(self, top_rank_threshold=85.0, atr_stop_mult=2.0, atr_target_mult=4.0):
        super().__init__("RsMomentum", {
            "top_rank_threshold": top_rank_threshold,
            "atr_stop_mult": atr_stop_mult, "atr_target_mult": atr_target_mult
        })
        self.top_rank = float(top_rank_threshold)
        self.atr_stop = float(atr_stop_mult)
        self.atr_target = float(atr_target_mult)

    def decide_from_rank(self, symbol, last_px, rank_pct, atr):
        if rank_pct >= self.top_rank:
            risk = max(atr * self.atr_stop, last_px * 0.005)
            return {
                "symbol": symbol, "action": "BUY", "side": "LONG", "price": float(last_px),
                "stop_loss": round(last_px - risk, 2), "target": round(last_px + self.atr_target * atr, 2),
                "atr": atr, "confidence": 80.0, "strategy": self.name,
                "reason": f"Top decile RS rank ({rank_pct:.1f}%) momentum leader"
            }
        return None
