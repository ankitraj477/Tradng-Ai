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
                target_premium = float(p.get("target") or (entry_credit * 0.50))
                stop_loss_premium = float(p.get("stop_loss") or (entry_credit * 2.0))
                expiry_date = str(p.get("expiry_date") or "")

                # 1. Expiry Day Final Square-Off (at 15:15 IST on expiry date)
                if expiry_date == today_str and is_expiry_square_off_time:
                    self.execution.close(symbol, current_premium, "Thursday Expiry Square-off")
                    closed += 1
                    continue

                # 2. 50% Profit-Taking Rule (Institutional High Win-Rate Edge)
                # When premium decays to <= 50% of credit collected, lock in profit!
                if current_premium <= target_premium:
                    self.execution.close(symbol, current_premium, "50% Profit Target (Theta Decayed)")
                    closed += 1
                    continue

                # 3. Stop Loss Rule (Premium expanded beyond 2x credit)
                if current_premium >= stop_loss_premium:
                    self.execution.close(symbol, current_premium, "Option Stop Loss (Adverse Move)")
                    closed += 1
                    continue

            except Exception as e:
                self.db.log("ERROR", f"FNO position manager error for {symbol}: {e!r}")

        return closed


FnoPositionManager = FNOPositionManager
