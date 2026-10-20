from .strategies import evaluate

class AITrader:
    """Auditable V9 decision engine with bounded regime-aware learning."""
    def __init__(self, learning=None, cfg=None):
        self.learning = learning
        self.cfg = cfg or {}

    def propose(self,c,regime,market_sentiment="Neutral"):
        sig=evaluate(c)
        weighted=[]
        for name,score in sig:
            w=self.learning.weight_for(name,regime) if self.learning else 1.0
            weighted.append((name,score*w,w))
        avg=sum(v for _,v,_ in weighted)/len(weighted)
        best=max(weighted,key=lambda x:x[1])
        news_bias=c.get("news_bias",0)

        # Direction-specific scoring
        bullish = c.get("ret_5", 0) > 0 and c.get("ret_20", 0) > 0 and c.get("rsi", 50) >= 50
        bearish = c.get("ret_5", 0) < 0 and c.get("ret_20", 0) < 0 and c.get("rsi", 50) <= 50

        long_score = avg + max(0, news_bias) + (5 if market_sentiment == "Bullish" else 0)

        # BUG-008: Direction-specific bearish signal evaluation
        ret_5 = c.get("ret_5", 0)
        ret_20 = c.get("ret_20", 0)
        rsi = c.get("rsi", 50)
        rel_vol = c.get("rel_volume", 1.0)
        bear_candidate_score = c.get("bear_score", c.get("score", 50))
        news_score = c.get("news_bias", 0)

        bear_signals = [
            ("Momentum", min(100, max(0, 50 - ret_5 * 500 + rel_vol * 10))),
            ("Breakout", 75 if bear_candidate_score >= 70 and rel_vol >= 1.0 else 45),
            ("Trend", 80 if ret_20 < 0 and rsi < 50 else 40),
            ("Mean Reversion", 70 if rsi > 65 else 35),
            ("News/Event", max(0, min(100, 50 - news_score * 2))),
        ]
        weighted_bear = []
        for name, score in bear_signals:
            w = self.learning.weight_for(name, regime) if self.learning else 1.0
            weighted_bear.append((name, score * w, w))
        bear_signal_avg = sum(v for _, v, _ in weighted_bear) / len(weighted_bear)
        short_score = bear_signal_avg + max(0, -news_bias) + (5 if market_sentiment == "Bearish" else 0)

        bull_score = c.get("bull_score", c["score"])
        bear_score = c.get("bear_score", c["score"])
        if bullish and bull_score >= 60 and long_score >= 65:
            action = "BUY"
            confidence = min(95, round(long_score))
            chosen_strat = best
            score_to_show = bull_score
        elif bearish and bear_score >= 60 and short_score >= 60 and market_sentiment in {"Bearish", "Neutral"}:
            action = "SHORT"
            confidence = min(95, round(short_score))
            chosen_strat = max(weighted_bear, key=lambda x: x[1])
            score_to_show = bear_score
        else:
            action = "WAIT"
            confidence = min(95, round(max(long_score, short_score)))
            chosen_strat = max(weighted_bear, key=lambda x: x[1]) if short_score > long_score else best
            score_to_show = bear_score if short_score > long_score else bull_score

        base_atr = max(c.get("atr", 0.0), c["price"] * 0.005)
        exec_cfg = self.cfg.get("execution", {})
        sl_pct = float(exec_cfg.get("stop_loss_pct", 0.0))
        tp_pct = float(exec_cfg.get("target_pct", 0.0))
        if sl_pct > 0 and tp_pct > 0:
            stop_dist = max(c["price"] * sl_pct, 1.5 * base_atr)
            target_dist = max(c["price"] * tp_pct, stop_dist * 2.0)
            atr = stop_dist / 1.5
        else:
            atr = base_atr
            stop_dist = 1.5 * atr
            target_dist = 3.0 * atr
        stop = c["price"] + stop_dist if action == "SHORT" else max(0.01, c["price"] - stop_dist)
        target = max(0.01, c["price"] - target_dist) if action == "SHORT" else c["price"] + target_dist
        rr = abs(target - c["price"]) / max(abs(c["price"] - stop), 0.01)
        reason = (f"{chosen_strat[0]} strongest; score {score_to_show:.0f}, RSI {c.get('rsi', 50):.1f}, "
                  f"5-bar return {c.get('ret_5', 0)*100:.2f}%, relative volume {c.get('rel_volume', 1.0):.2f}x; "
                  f"market={regime}; news bias={news_bias:+d}; learned weight={chosen_strat[2]:.2f}.")
        return {"symbol": c["symbol"], "action": action, "price": c["price"], "confidence": confidence,
                "strategy": chosen_strat[0], "reason": reason, "stop_loss": stop, "target": target,
                "risk_reward": rr, "sector": c.get("sector", "Unknown"), "regime": regime, "atr": atr}

