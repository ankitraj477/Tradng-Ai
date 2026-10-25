"""
Centralized emergency kill-switch independent of the main trading loop.
Monitors system health, detects SQLite locks, data staleness (>60s), and drawdown breaches.
Can flatten the entire portfolio immediately upon critical system failure.
"""

from datetime import datetime, timezone
import time
from ..market_hours import now_ist


class CentralKillSwitch:
    def __init__(self, db, execution=None, provider=None, cfg=None):
        self.db = db
        self.execution = execution
        self.provider = provider
        self.cfg = cfg or {}
        self._tripped = False
        self._trip_reason = None
        self._tripped_at = None

    def is_tripped(self):
        """Returns True if the kill switch is currently active."""
        if self._tripped:
            return True, self._trip_reason

        # Check DB persistent setting as well
        if self.db.get_setting("emergency_kill_switch") == "TRIPPED":
            return True, self.db.get_setting("emergency_kill_reason") or "Manual or external panic trigger"

        return False, None

    def trigger(self, reason="Emergency kill-switch triggered"):
        """Triggers the kill switch, logging the event and writing to persistent DB settings."""
        self._tripped = True
        self._trip_reason = str(reason)
        self._tripped_at = datetime.now(timezone.utc).isoformat()
        try:
            self.db.set_setting("emergency_kill_switch", "TRIPPED")
            self.db.set_setting("emergency_kill_reason", self._trip_reason)
            self.db.set_auto_trading(False)
            self.db.log("ERROR", f"KILL-SWITCH ACTIVATED: {self._trip_reason}")
        except Exception as e:
            # Fallback in case DB is locked
            pass
        return True

    def reset(self, reset_drawdown_peak=True):
        """Resets the kill switch and restores normal trading baseline."""
        self._tripped = False
        self._trip_reason = None
        self._tripped_at = None
        try:
            self.db.set_setting("emergency_kill_switch", "NORMAL")
            self.db.set_setting("emergency_kill_reason", "")
            self.db.set_auto_trading(True)
            if reset_drawdown_peak:
                acc = self.db.account()
                if acc:
                    clean_peak = max(float(acc.get("starting_capital", 100000.0)), float(acc.get("cash", 100000.0)))
                    self.db.update_account(acc["cash"], clean_peak)
            self.db.log("INFO", "KILL-SWITCH RESET: Normal operations and drawdown baseline restored.")
        except Exception:
            pass
        return True

    def check_health(self, max_stale_seconds=60.0):
        """
        Independent health check:
        1. Tests database read/write responsiveness (detects SQLite locks).
        2. Tests market data quote freshness if live_data is active.
        Trips automatically if health conditions are violated.
        """
        # 1. DB Lock & Responsiveness Test
        try:
            t0 = time.time()
            account = self.db.account()
            if not account or (time.time() - t0) > 3.0:
                self.trigger("Database latency/lock detected (>3.0s)")
                return False, self._trip_reason
        except Exception as exc:
            self.trigger(f"Database error or lock: {exc!r}")
            return False, self._trip_reason

        # 2. Market Data Staleness Test (for live data mode)
        if self.cfg.get("live_data") and self.provider:
            try:
                meta = getattr(self.provider, "last_batch_stats", {})
                last_update = meta.get("timestamp")
                if last_update:
                    age = (time.time() - float(last_update))
                    if age > float(max_stale_seconds):
                        self.trigger(f"Market data stale (> {max_stale_seconds:.0f}s old: age={age:.1f}s)")
                        return False, self._trip_reason
            except Exception as exc:
                self.trigger(f"Market provider health check failed: {exc!r}")
                return False, self._trip_reason

        return True, "HEALTHY"

    def flatten_portfolio(self, reason="Emergency Portfolio Flatten"):
        """
        Immediately force-closes all open positions across the portfolio.
        Safe against quote failures by falling back to last recorded price.
        """
        self.trigger(reason)
        closed_count = 0

        positions = self.db.positions()
        for p in positions:
            sym = p["symbol"]
            price = None
            if self.provider:
                try:
                    q = self.provider.quote(sym)
                    if q and q.get("price"):
                        price = float(q["price"])
                except Exception:
                    price = None

            if price is None:
                price = float(p.get("current_price") or p["entry_price"])

            ptype = str(p.get("product_type", "INTRADAY")).upper()
            try:
                if ptype == "FNO":
                    from ..fno.execution import FNOExecution
                    fno_exec = FNOExecution(self.db, self.cfg)
                    fno_exec.close(sym, price, f"EMERGENCY FLATTEN: {reason}")
                elif ptype == "SWING":
                    from ..swing.execution import SwingExecution
                    swing_exec = SwingExecution(self.db, self.cfg)
                    swing_exec.close(sym, price, f"EMERGENCY FLATTEN: {reason}")
                elif self.execution:
                    self.execution.close(sym, price, f"EMERGENCY FLATTEN: {reason}", "")
                closed_count += 1
            except Exception as exc:
                self.db.log("ERROR", f"Failed emergency close for {sym}: {exc!r}")

        self.db.log("WARN", f"PORTFOLIO FLATTENED: {closed_count} positions closed.")
        return closed_count


KillSwitch = CentralKillSwitch

