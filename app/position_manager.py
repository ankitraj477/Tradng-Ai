from datetime import datetime, timezone, time
import time as _time
from .market_hours import now_ist, holiday_name
from .indicators import indicators
from .intraday.timing import IntradayTimingManager

class PositionManager:
    """Deterministic fast protection for paper positions. AI never controls these exits."""
    def __init__(self, db, execution, provider, cfg):
        self.db=db; self.execution=execution; self.provider=provider; self.cfg=cfg
        self._last_err={}
        self.timing = IntradayTimingManager()

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

    def manage(self, dt=None):
        closed=0; mult=float(self.cfg["execution"].get("trailing_stop_atr",1.5)); max_minutes=float(self.cfg["execution"].get("max_hold_minutes",390))
        check_dt = dt if dt is not None else (now_ist() if self.cfg.get("live_data", False) else None)
        is_eod = self.timing.must_square_off(check_dt) if check_dt else False
        for p in self.db.positions():
            try:
                try:
                    q=self.provider.quote(p["symbol"])
                    price=float(q["price"]) if q else None
                except Exception as e:
                    price=None
                    t_now=_time.time()
                    if t_now - self._last_err.get(p["symbol"], 0) >= 900:
                        self._last_err[p["symbol"]]=t_now
                        self.db.log("WARN", f"Quote unavailable for {p['symbol']}: {e!r}")
                if price is None:
                    if is_eod: price=float(p.get("current_price") or p["entry_price"])
                    else: continue
                if is_eod:
                    self.execution.close(p["symbol"],price,"EOD square-off",""); closed+=1; continue
                atr=self._atr_for_position(p); age=0
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
