"""
Swing Position Manager.
Manages multi-day delivery positions across sessions.
CRITICAL RULE: Swing positions are EXEMPT from 15:10 IST intraday square-off.
Implements multi-day breakeven locks and dynamic target expansions.
"""

class SwingPositionManager:
    def __init__(self, db, execution, provider, cfg=None):
        self.db = db
        self.execution = execution
        self.provider = provider
        self.cfg = cfg or {}

    def manage(self) -> int:
        """
        Evaluate and protect all open SWING positions.
        Returns number of positions closed.
        """
        closed = 0
        positions = self.db.positions_by_product("SWING")

        for p in positions:
            symbol = p["symbol"]
            try:
                # Fetch quote
                q = self.provider.quote(symbol) if hasattr(self.provider, "quote") else None
                price = float(q["price"]) if q and "price" in q else None
                if price is None:
                    continue

                p["current_price"] = price
                with self.db.conn() as c:
                    c.execute("UPDATE positions SET current_price=? WHERE symbol=?", (price, symbol))

                entry = float(p["entry_price"])
                stop = float(p["stop_loss"]) if p.get("stop_loss") is not None else None
                target = float(p["target"]) if p.get("target") is not None else None
                target_step = float(p.get("target_step") or 0.0)
                if target_step <= 0.0 and target is not None:
                    target_step = abs(target - entry)
                days_held = int(p.get("days_held") or 0)

                # 1. Hard Stop Loss Check
                if stop is not None and price <= stop:
                    self.execution.close(symbol, price, "Swing Stop Loss")
                    closed += 1
                    continue

                # 2. Time-Based Stagnation Exit (Max 25 trading days)
                max_days = int(self.cfg.get("swing", {}).get("max_holding_days", 25))
                if days_held >= max_days:
                    self.execution.close(symbol, price, f"Time exit (held {days_held} days)")
                    closed += 1
                    continue

                # 3. Dynamic Target Expansion (Multi-Day Runner)
                if target is not None and price >= target:
                    dynamic_expansion = self.cfg.get("swing", {}).get("dynamic_target_expansion", True)
                    if dynamic_expansion:
                        buffer = round(target_step * 0.33, 2)
                        new_stop = max(stop if stop is not None else 0.0, round(target - buffer, 2))
                        new_target = round(target + target_step, 2)

                        self.db.update_stop_and_target(symbol, new_stop, new_target)
                        self.db.log(
                            "INFO",
                            f"SWING TARGET EXPANDED: {symbol} reached {price:.2f} (target {target:.2f}). "
                            f"SL ratcheted to {new_stop:.2f} (locked profit: +₹{(new_stop - entry):.2f}/sh), "
                            f"new target: {new_target:.2f}"
                        )
                        stop = new_stop
                        target = new_target
                    else:
                        self.execution.close(symbol, price, "Swing Target Reached")
                        closed += 1
                        continue

                # 4. Breakeven Lock at 50% distance to target
                if target is not None and target > entry:
                    halfway_trigger = entry + 0.50 * target_step
                    if price >= halfway_trigger and (stop is None or stop < entry):
                        # Cover delivery costs with 0.3% buffer
                        be_stop = round(entry * 1.003, 2)
                        new_stop = max(stop if stop is not None else 0.0, be_stop)
                        if stop is None or new_stop > stop:
                            self.db.update_stop(symbol, new_stop)
                            self.db.log(
                                "INFO",
                                f"SWING BREAKEVEN LOCK: {symbol} reached {price:.2f} (>= {halfway_trigger:.2f}). "
                                f"Stop ratcheted to {new_stop:.2f}"
                            )

            except Exception as e:
                self.db.log("ERROR", f"Swing manager error for {symbol}: {e!r}")

        return closed
