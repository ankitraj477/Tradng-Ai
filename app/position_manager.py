from datetime import datetime, timezone
from .indicators import indicators

class PositionManager:
    """Deterministic fast protection for paper positions. AI never controls these exits."""
    def __init__(self, db, execution, provider, cfg):
        self.db=db; self.execution=execution; self.provider=provider; self.cfg=cfg

    def _atr_for_position(self, p):
        atr=float(p.get("atr",0) or 0)
        if atr>0: return atr
        # Recovery path for positions created by older database schemas.
        try:
            df=self.provider.history(p["symbol"],period="5d",interval="5m")
            x=indicators(df)
            if not x.empty and float(x.iloc[-1].get("atr",0) or 0)>0:
                atr=float(x.iloc[-1]["atr"]); self.db.update_position_atr(p["symbol"],atr)
        except Exception as e:
            self.db.log("WARN",f"ATR unavailable for {p['symbol']}: {e!r}")
        return atr

    def manage(self):
        closed=0; mult=float(self.cfg["execution"].get("trailing_stop_atr",1.0)); max_minutes=float(self.cfg["execution"].get("max_hold_minutes",390))
        for p in self.db.positions():
            try:
                q=self.provider.quote(p["symbol"])
                if not q: continue
                price=float(q["price"]); atr=self._atr_for_position(p); age=0
                if p.get("opened_at"):
                    try: age=max(0,(datetime.now(timezone.utc)-datetime.fromisoformat(str(p["opened_at"]).replace("Z","+00:00"))).total_seconds()/60)
                    except Exception: pass
                stop=float(p["stop_loss"]) if p.get("stop_loss") is not None else None
                target=float(p["target"])

                # First test the existing stop. A trailing stop is ratcheted only
                # after the current price survives the existing protection level.
                if p["side"]=="LONG":
                    if stop is not None and price<=stop:
                        self.execution.close(p["symbol"],price,"Stop loss",""); closed+=1; continue
                    if price>=target:
                        self.execution.close(p["symbol"],price,"Target reached",""); closed+=1; continue
                    if age>=max_minutes:
                        self.execution.close(p["symbol"],price,"Time exit",""); closed+=1; continue
                    if atr>0 and stop is not None:
                        new_stop=max(stop,price-mult*atr); self.db.update_stop(p["symbol"],new_stop)
                else:
                    if stop is not None and price>=stop:
                        self.execution.close(p["symbol"],price,"Short stop loss",""); closed+=1; continue
                    if price<=target:
                        self.execution.close(p["symbol"],price,"Short target reached",""); closed+=1; continue
                    if age>=max_minutes:
                        self.execution.close(p["symbol"],price,"Time exit",""); closed+=1; continue
                    if atr>0 and stop is not None:
                        new_stop=min(stop,price+mult*atr); self.db.update_stop(p["symbol"],new_stop)
            except Exception as e: self.db.log("ERROR",f"Position manager {p['symbol']}: {e!r}")
        return closed
