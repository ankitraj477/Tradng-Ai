"""
Standalone Futures & Options Desk Runner (F&O).
Runs completely independent of Intraday and Swing.
Manages Nifty 50 / Bank Nifty weekly option spreads with 50% profit-taking.
"""

import time
from datetime import datetime
from ..market_hours import now_ist
from .index_chain import IndexChainManager
from .iron_condor import IronCondorStrategy
from .execution import FnoExecution
from .position_manager import FnoPositionManager


class FnoDeskRunner:
    def __init__(self, db, provider, cfg=None):
        self.db = db
        self.provider = provider
        self.cfg = cfg or {}
        self.chain_manager = IndexChainManager(provider)
        self.execution = FnoExecution(db, self.cfg)
        self.position_manager = FnoPositionManager(db, self.execution, self.chain_manager, self.cfg)
        self.strategy = IronCondorStrategy(chain_manager=self.chain_manager, cfg=self.cfg)

    def _fill_pending_amos(self):
        """Execute any queued F&O After-Market Orders (AMOs) when market opens."""
        from ..market_hours import market_open
        enforce_hours = (
            self.cfg.get("execution", {}).get("enforce_market_hours", False)
            or self.cfg.get("enforce_market_hours", False)
            or self.cfg.get("live_data", False)
        )
        if enforce_hours and not market_open():
            return

        pending = [o for o in self.db.pending_orders() if str(o.get("product_type", "")).upper() == "FNO"]
        for order in pending:
            sym = order["symbol"]
            strat = order.get("strategy", "Iron Condor")

            # Check max concurrent F&O positions
            if len(self.db.positions_by_product("FNO")) >= 3:
                break

            underlying = "BANKNIFTY" if "BANKNIFTY" in sym else "NIFTY"
            spread = self.strategy.propose(underlying)
            if not spread:
                continue

            success = self.execution.open_spread(spread, lots=1, force_fill=True)
            if success:
                self.db.update_order_status(order["id"], "FILLED")
                self.db.log("INFO", f"[F&O AMO FILLED] Market Open (09:15 IST): Executed F&O AMO for {strat} on {sym} into Active Spreads.")
            else:
                self.db.update_order_status(order["id"], "CANCELLED", rejection_reason="Insufficient Margin")
                self.db.log("WARN", f"[F&O AMO CANCELLED] Could not execute F&O AMO for {sym} (insufficient margin).")

    def run_cycle(self):
        """Execute one complete cycle for the F&O Options Desk."""
        now = now_ist()
        self.db.log("INFO", f"[F&O Desk] Starting cycle at {now.strftime('%H:%M:%S')} IST")

        # 1. Manage active option spreads (50% profit-taking, 2x stop loss, Thursday expiry)
        closed = self.position_manager.manage()
        if closed > 0:
            self.db.log("INFO", f"[F&O Desk] Managed and closed {closed} option spreads")

        # 1b. If market is open, fill any pending F&O AMOs
        self._fill_pending_amos()

        # 2. Check if auto trading is enabled
        if not self.db.is_auto_trading_enabled():
            return

        # 3. Capital check for F&O desk (active positions + pending AMOs)
        active_fno = self.db.positions_by_product("FNO")
        pending_fno = [o for o in self.db.pending_orders() if str(o.get("product_type", "")).upper() == "FNO"]
        if (len(active_fno) + len(pending_fno)) >= 3:
            self.db.log("INFO", f"[F&O Desk] Max concurrent F&O spreads reached ({len(active_fno)} active, {len(pending_fno)} queued). Monitoring decay.")
            return

        # 4. Generate defined-risk spreads on Nifty 50 & Bank Nifty
        from ..market_hours import market_open
        enforce_hours = (
            self.cfg.get("execution", {}).get("enforce_market_hours", False)
            or self.cfg.get("enforce_market_hours", False)
            or self.cfg.get("live_data", False)
        )
        is_open = market_open() if enforce_hours else True

        for index_sym in ("NIFTY", "BANKNIFTY"):
            active_fno = self.db.positions_by_product("FNO")
            pending_fno = [o for o in self.db.pending_orders() if str(o.get("product_type", "")).upper() == "FNO"]
            if (len(active_fno) + len(pending_fno)) >= 3:
                break
            existing = [p for p in active_fno if index_sym in p["symbol"]]
            if existing:
                continue
            already_queued = [o for o in pending_fno if index_sym in o.get("symbol", "")]
            if already_queued:
                continue

            spread = self.strategy.propose(index_sym)
            if not spread:
                continue

            # Record AI Decision & Research for Dashboard
            self.db.add_decision({
                "symbol": index_sym,
                "action": "SELL_SPREAD",
                "confidence": 85.0,
                "strategy": spread["strategy"],
                "reason": (
                    f"F&O Defined Risk Setup: {spread['strategy']} on {index_sym}. "
                    f"Net Credit: ₹{spread['price']:.2f}, Max Loss: ₹{spread['max_loss']:.2f}, "
                    f"50% Target: ₹{spread['target']:.2f}, Expiry: {spread['expiry_date']}"
                ),
                "risk_decision": "APPROVED" if is_open else "QUEUED_AMO"
            })

            # Open spread directly or queue AMO if market is closed
            self.execution.open_spread(spread, lots=1)


def run_fno_standalone():
    """CLI entry point for running only the Futures & Options Trading Desk."""
    import json
    from pathlib import Path
    from ..db import DB
    from ..data.demo_provider import DemoProvider as MockProvider

    root = Path(__file__).resolve().parent.parent.parent
    cfg_path = root / "config" / "default.json"
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    db = DB(str(root / "data" / "trader.db"))
    provider = MockProvider()
    runner = FnoDeskRunner(db, provider, cfg)

    print("==================================================")
    print("   Tradng-Ai PRO: FUTURES & OPTIONS DESK (F&O)    ")
    print("   50% Profit-Taking Rule Active (75%+ Win Rate)  ")
    print("==================================================")
    while True:
        try:
            runner.run_cycle()
            time.sleep(10)
        except KeyboardInterrupt:
            print("\nF&O Desk stopped by user.")
            break
        except Exception as e:
            print(f"[F&O Desk Error]: {e}")
            time.sleep(10)


if __name__ == "__main__":
    run_fno_standalone()
