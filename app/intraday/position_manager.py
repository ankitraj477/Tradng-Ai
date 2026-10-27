from datetime import datetime, timezone, time
import time as _time
from ..market_hours import now_ist
from ..indicators import indicators
from .timing import IntradayTimingManager


class IntradayPositionManager:
    """
    Dedicated Intraday (MIS) Position Manager.
    
    Responsibilities:
    1. Enforce strict 15:10 IST EOD auto square-off for intraday MIS positions.
    2. Manage dynamic stop loss ratcheting:
       - Breakeven lock at +50% progress toward target.
       - Dynamic runner expansion if technical continuation momentum is alive.
       - Continuous ATR trailing stop between milestones.
    3. Guarantees complete isolation from Swing and F&O positions.
    """

    def __init__(self, db, execution, provider, cfg):
        self.db = db
        self.execution = execution
        self.provider = provider
        self.cfg = cfg or {}
        self._last_err = {}
        self.timing = IntradayTimingManager()
        self._quote_fail_count = {}
        self._outage_alerted = set()

    def _atr_for_position(self, p):
        atr = float(p.get("atr", 0) or 0)
        if atr > 0:
            return atr
        if not hasattr(self.provider, "history") or not callable(getattr(self.provider, "history", None)):
            return 0.0
        try:
            df = self.provider.history(p["symbol"], period="5d", interval="5m")
            x = indicators(df)
            if not x.empty and float(x.iloc[-1].get("atr", 0) or 0) > 0:
                atr = float(x.iloc[-1]["atr"])
                self.db.update_position_atr(p["symbol"], atr)
        except Exception as e:
            self.db.log("WARN", f"[Intraday] ATR unavailable for {p['symbol']}: {e!r}")
        return atr

    def catch_up_close(self):
        """Close any intraday positions that survived past 15:30 IST market close."""
        positions = self.db.positions()
        closed = 0
        for p in positions:
            if p.get("product_type", "INTRADAY").upper() != "INTRADAY":
                continue
            try:
                try:
                    q = self.provider.quote(p["symbol"])
                    price = float(q["price"]) if q else None
                except Exception:
                    price = None

                if price is None:
                    price = float(p.get("current_price") or p["entry_price"])

                self.execution.close(p["symbol"], price, "Catch-up close (missed EOD)", "")
                closed += 1
                self.db.log("WARN", f"[Intraday] CATCH-UP CLOSE: {p['symbol']} closed at {price:.2f}")
            except Exception as e:
                self.db.log("ERROR", f"[Intraday] Catch-up close failed for {p['symbol']}: {e!r}")
        return closed

    def _has_continuation_potential(self, p, price, side, check_dt=None):
        exec_cfg = self.cfg.get("execution", {})
        if not exec_cfg.get("dynamic_target_expansion", True):
            return False

        if check_dt is not None:
            t = check_dt.time() if hasattr(check_dt, "time") else None
            if t and t >= time(15, 0):
                return False

        if hasattr(self.provider, "history"):
            try:
                df = self.provider.history(p["symbol"], period="2d", interval="5m")
                x = indicators(df)
                if not x.empty and "rsi" in x.columns:
                    rsi_val = float(x.iloc[-1].get("rsi", 50.0))
                    if side == "LONG" and rsi_val >= 88.0:
                        return False
                    if side == "SHORT" and rsi_val <= 12.0:
                        return False
            except Exception:
                pass

        return True

    def _sync_bracket_stop(self, symbol, new_stop):
        """Synchronizes dynamic trailing or breakeven stop loss changes to BracketOrderManager."""
        if hasattr(self.execution, "bracket_manager"):
            try:
                self.execution.bracket_manager.update_stop_loss(symbol, new_stop)
            except Exception:
                pass

    def manage(self, dt=None):
        closed = 0
        exec_cfg = self.cfg.get("execution", {})
        mult = float(exec_cfg.get("trailing_stop_atr", 1.5))
        max_minutes = float(exec_cfg.get("max_hold_minutes", 390))
        dynamic_target_expansion = exec_cfg.get("dynamic_target_expansion", True)
        breakeven_lock_ratio = float(exec_cfg.get("breakeven_lock_ratio", 0.50))
        buffer_ratio = float(exec_cfg.get("trailing_buffer_ratio", 1.0 / 3.0))

        check_dt = dt if dt is not None else (now_ist() if self.cfg.get("live_data", False) else None)
        is_eod = self.timing.must_square_off(check_dt) if check_dt else False
        max_consecutive_failures = int(self.cfg.get("risk", {}).get("max_quote_failures", 12))

        for p in self.db.positions():
            # STRICT DECOUPLING: Only manage intraday MIS positions
            if p.get("product_type", "INTRADAY").upper() != "INTRADAY":
                continue
            try:
                try:
                    q = self.provider.quote(p["symbol"])
                    price = float(q["price"]) if q else None
                    self._quote_fail_count[p["symbol"]] = 0
                    if p["symbol"] in self._outage_alerted:
                        self._outage_alerted.discard(p["symbol"])
                        self.db.log("INFO", f"[Intraday] Quote restored for {p['symbol']}")
                except Exception as e:
                    price = None
                    self.db.count_exception("protection")
                    self._quote_fail_count[p["symbol"]] = self._quote_fail_count.get(p["symbol"], 0) + 1
                    fail_count = self._quote_fail_count[p["symbol"]]

                    t_now = _time.time()
                    if t_now - self._last_err.get(p["symbol"], 0) >= 900:
                        self._last_err[p["symbol"]] = t_now
                        self.db.log("WARN", f"[Intraday] Quote unavailable for {p['symbol']}: {e!r} (failures: {fail_count})")

                    if fail_count >= max_consecutive_failures and p["symbol"] not in self._outage_alerted:
                        self._outage_alerted.add(p["symbol"])
                        self.db.log("ERROR", f"[Intraday] QUOTE OUTAGE: {p['symbol']} has {fail_count} consecutive failures.")

                if price is None:
                    if is_eod:
                        price = float(p.get("current_price") or p["entry_price"])
                    else:
                        continue

                # Enforce 15:10 IST EOD auto square-off
                if is_eod:
                    self.execution.close(p["symbol"], price, "EOD square-off", "")
                    closed += 1
                    continue

                p["current_price"] = price
                self.execution.mark([{"symbol": p["symbol"], "price": price}])
                atr = self._atr_for_position(p)
                age = 0
                if p.get("opened_at"):
                    try:
                        age = max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(str(p["opened_at"]).replace("Z", "+00:00"))).total_seconds() / 60)
                    except Exception:
                        pass

                stop = float(p["stop_loss"]) if p.get("stop_loss") is not None else None
                target = float(p["target"]) if p.get("target") is not None else None
                entry = float(p["entry_price"])
                target_step = float(p.get("target_step") or 0.0)
                if target_step <= 0.0 and target is not None:
                    target_step = abs(target - entry)

                if p["side"] == "LONG":
                    if stop is not None and price <= stop:
                        self.execution.close(p["symbol"], price, "Stop loss", "")
                        closed += 1
                        continue
                    if age >= max_minutes:
                        self.execution.close(p["symbol"], price, "Time exit", "")
                        closed += 1
                        continue

                    # Dynamic target expansion or standard target exit
                    if target is not None and price >= target:
                        if dynamic_target_expansion and self._has_continuation_potential(p, price, "LONG", check_dt):
                            expansions = 0
                            step = target_step
                            if atr > 0:
                                step = max(step, round(1.0 * atr, 2))
                            step = max(step, round(entry * 0.01, 2))
                            buffer = max(round(step * buffer_ratio, 2), 0.01)

                            while target is not None and price >= target and expansions < 10:
                                new_stop = max(stop if stop is not None else 0.0, round(target - buffer, 2))
                                new_target = round(target + step, 2)
                                self.db.update_stop_and_target(p["symbol"], new_stop, new_target)
                                self._sync_bracket_stop(p["symbol"], new_stop)
                                self.db.log(
                                    "INFO",
                                    f"[Intraday] DYNAMIC TARGET EXPANDED: {p['symbol']} reached {price:.2f}. "
                                    f"SL ratcheted to {new_stop:.2f}, new target {new_target:.2f}"
                                )
                                stop = new_stop
                                target = new_target
                                expansions += 1
                        else:
                            self.execution.close(p["symbol"], price, "Target reached", "")
                            closed += 1
                            continue

                    # Breakeven lock when price is >= 50% to target
                    if target is not None and target > entry:
                        halfway_trigger = entry + breakeven_lock_ratio * target_step
                        if price >= halfway_trigger and (stop is None or stop < entry):
                            be_stop = round(entry * 1.001, 2)
                            new_stop = max(stop if stop is not None else 0.0, be_stop)
                            if stop is None or new_stop > stop:
                                self.db.update_stop(p["symbol"], new_stop)
                                self._sync_bracket_stop(p["symbol"], new_stop)
                                self.db.log("INFO", f"[Intraday] BREAKEVEN LOCK: {p['symbol']} at {price:.2f}. SL moved to {new_stop:.2f}")
                                stop = new_stop

                    # Continuous ATR trailing stop
                    if atr > 0 and stop is not None:
                        new_stop = max(stop, round(price - mult * atr, 2))
                        if new_stop > stop:
                            self.db.update_stop(p["symbol"], new_stop)
                            self._sync_bracket_stop(p["symbol"], new_stop)
                            stop = new_stop
                else:
                    if stop is not None and price >= stop:
                        self.execution.close(p["symbol"], price, "Short stop loss", "")
                        closed += 1
                        continue
                    if age >= max_minutes:
                        self.execution.close(p["symbol"], price, "Time exit", "")
                        closed += 1
                        continue

                    # Dynamic target expansion or standard target exit
                    if target is not None and price <= target:
                        if dynamic_target_expansion and self._has_continuation_potential(p, price, "SHORT", check_dt):
                            expansions = 0
                            step = target_step
                            if atr > 0:
                                step = max(step, round(1.0 * atr, 2))
                            step = max(step, round(entry * 0.01, 2))
                            buffer = max(round(step * buffer_ratio, 2), 0.01)

                            while target is not None and price <= target and expansions < 10:
                                new_stop = min(stop if stop is not None else float("inf"), round(target + buffer, 2))
                                new_target = max(0.01, round(target - step, 2))
                                self.db.update_stop_and_target(p["symbol"], new_stop, new_target)
                                self._sync_bracket_stop(p["symbol"], new_stop)
                                self.db.log(
                                    "INFO",
                                    f"[Intraday] DYNAMIC TARGET EXPANDED: {p['symbol']} reached {price:.2f}. "
                                    f"SL ratcheted to {new_stop:.2f}, new target {new_target:.2f}"
                                )
                                stop = new_stop
                                target = new_target
                                expansions += 1
                        else:
                            self.execution.close(p["symbol"], price, "Short target reached", "")
                            closed += 1
                            continue

                    # Breakeven lock when price is >= 50% to target
                    if target is not None and target < entry:
                        halfway_trigger = entry - breakeven_lock_ratio * target_step
                        if price <= halfway_trigger and (stop is None or stop > entry):
                            be_stop = round(entry * 0.999, 2)
                            new_stop = min(stop if stop is not None else float("inf"), be_stop)
                            if stop is None or new_stop < stop:
                                self.db.update_stop(p["symbol"], new_stop)
                                self._sync_bracket_stop(p["symbol"], new_stop)
                                self.db.log("INFO", f"[Intraday] BREAKEVEN LOCK: {p['symbol']} at {price:.2f}. SL moved to {new_stop:.2f}")
                                stop = new_stop

                    # Continuous ATR trailing stop
                    if atr > 0 and stop is not None:
                        new_stop = min(stop, round(price + mult * atr, 2))
                        if new_stop < stop:
                            self.db.update_stop(p["symbol"], new_stop)
                            self._sync_bracket_stop(p["symbol"], new_stop)
                            stop = new_stop
            except Exception as e:
                self.db.log("ERROR", f"[Intraday] Position manager {p['symbol']}: {e!r}")
        return closed

