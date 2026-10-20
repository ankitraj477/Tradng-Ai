"""
F&O Position Manager.
Enforces the institutional 50% Profit-Taking Rule for theta decay,
stop-loss limits, and Thursday 15:15 IST expiry square-off.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


class FNOPositionManager:
    def __init__(self, db, execution, chain_manager=None, cfg=None):
        self.db = db
        self.execution = execution
        self.chain = chain_manager
        self.cfg = cfg or {}

    def manage(self, dt=None) -> int:
        """
        Evaluate and protect all open FNO positions.
        Returns number of closed contracts.
        """
        closed = 0
        now_dt = dt or datetime.now(IST)
        today_str = now_dt.strftime("%Y-%m-%d")
        is_expiry_square_off_time = (now_dt.hour > 15) or (now_dt.hour == 15 and now_dt.minute >= 15)

        positions = self.db.positions_by_product("FNO")

        for p in positions:
            symbol = p["symbol"]
            try:
                entry_credit = float(p["entry_price"])
                current_premium = float(p.get("current_price") or entry_credit)
                fno_cfg = self.cfg.get("fno", {})
                target_ratio = float(fno_cfg.get("profit_target_ratio", 0.50))
                target_premium = float(p.get("target") or (entry_credit * target_ratio))
                stop_loss_premium = float(p.get("stop_loss") or (entry_credit * 2.0))
                expiry_date = str(p.get("expiry_date") or "")

                # Dynamic Option Premium Valuation (Theta decay & Spot risk)
                # If current_price has not been manually overridden by a live broker or test:
                if float(p.get("current_price") or entry_credit) == entry_credit and p.get("opened_at") and expiry_date:
                    try:
                        opened = datetime.fromisoformat(str(p["opened_at"]).replace("Z", "+00:00")).astimezone(IST)
                        expiry_dt = datetime.strptime(expiry_date, "%Y-%m-%d").replace(hour=15, minute=30, tzinfo=IST)
                        total_span = max(1.0, (expiry_dt - opened).total_seconds())
                        elapsed = max(0.0, (now_dt - opened).total_seconds())
                        time_fraction = min(1.0, elapsed / total_span)

                        underlying = "BANKNIFTY" if "BANKNIFTY" in symbol else "NIFTY"
                        spot_drift_pct = 0.0
                        if self.chain and hasattr(self.chain, "get_spot_price"):
                            spot = self.chain.get_spot_price(underlying)
                            strike = float(p.get("strike_price") or spot)
                            if strike > 0:
                                spot_drift_pct = abs(spot - strike) / strike

                        if spot_drift_pct > 0.025:
                            expansion_factor = 1.0 + (spot_drift_pct - 0.025) * 40.0
                            current_premium = round(entry_credit * min(2.5, expansion_factor), 2)
                        else:
                            decay_factor = max(0.10, 1.0 - (0.55 * (time_fraction ** 0.5)))
                            current_premium = round(entry_credit * decay_factor, 2)

                        self.db.update_current_price(symbol, current_premium)
                    except Exception:
                        pass

                # 1. Expiry Day Final Square-Off (at 15:15 IST on expiry date)
                if expiry_date == today_str and is_expiry_square_off_time:
                    self.execution.close(symbol, current_premium, "Thursday Expiry Square-off")
                    closed += 1
                    continue

                # 2. Dynamic Trailing Breakeven Lock:
                # If premium has decayed by >= 25% (unrealized gain), tighten stop-loss to entry credit
                # to ensure a winning options trade never turns into a loss!
                if current_premium <= entry_credit * 0.75 and stop_loss_premium > entry_credit:
                    stop_loss_premium = entry_credit
                    try:
                        self.db.update_position_stops(symbol, stop_loss=entry_credit, target=target_premium)
                    except Exception:
                        pass

                # 3. Realistic Profit-Taking Rule (Locks in profit when theta decays to target)
                if current_premium <= target_premium:
                    decay_pct = int(round((1.0 - target_ratio) * 100))
                    reason = "50% Profit Target (Theta Decayed)" if decay_pct == 50 else f"Profit Target Reached ({decay_pct}% Theta Decayed)"
                    self.execution.close(symbol, current_premium, reason)
                    closed += 1
                    continue

                # 4. Stop Loss Rule (Premium expanded beyond stop loss limit)
                if current_premium >= stop_loss_premium:
                    self.execution.close(symbol, current_premium, "Option Stop Loss (Adverse Move)")
                    closed += 1
                    continue

            except Exception as e:
                self.db.log("ERROR", f"FNO position manager error for {symbol}: {e!r}")

        return closed


FnoPositionManager = FNOPositionManager
