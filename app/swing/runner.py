"""
Standalone Stocks / Swing Trading Desk Runner (CNC Cash Delivery).
Runs completely independent of Intraday and F&O.
Exempt from 15:10 IST EOD square-off; positions held 3 to 20 days.
"""

import time
from datetime import datetime
from ..market_hours import now_ist, market_open
from ..universe import get_universe_symbols
from .scanner import Stage2SwingScanner
from .pullback_strategy import SwingPullbackStrategy
from .execution import SwingExecution
from .position_manager import SwingPositionManager


class SwingDeskRunner:
    def __init__(self, db, provider, cfg=None):
        self.db = db
        self.provider = provider
        self.cfg = cfg or {}
        self.execution = SwingExecution(db, self.cfg)
        self.position_manager = SwingPositionManager(db, self.execution, provider, self.cfg)
        self.scanner = Stage2SwingScanner(provider)
        self.strategy = SwingPullbackStrategy(provider)

    def run_cycle(self):
        """Execute one complete cycle for the Swing Trading Desk."""
        now = now_ist()
        self.db.log("INFO", f"[Swing Desk] Starting cycle at {now.strftime('%H:%M:%S')} IST")

        # 1. Manage active swing delivery holdings (breakeven lock, dynamic multi-day runner, max 25-day hold)
        closed = self.position_manager.manage()
        if closed > 0:
            self.db.log("INFO", f"[Swing Desk] Managed and closed {closed} swing delivery positions")

        # 2. Check if auto trading is enabled
        if not self.db.is_auto_trading_enabled():
            return

        # 3. Capital check for swing desk
        alloc = self.db.get_capital_allocation()
        swing_alloc_pct = alloc.get("swing", 40.0) / 100.0
        account = self.db.account()
        starting = account.get("starting_capital", 100000.0) if account else 100000.0
        max_swing_desk_capital = starting * swing_alloc_pct

        # Count active swing positions
        active_swing = self.db.positions_by_product("SWING")
        if len(active_swing) >= 5:
            self.db.log("INFO", f"[Swing Desk] Max concurrent swing holdings reached (5). Monitoring active trades.")
            return

        # 4. Scan for Stage 2 Trend Template & 20 EMA Pullback candidates
        universe = get_universe_symbols()
        candidates = self.scanner.scan_stage2_candidates(universe[:40])
        for cand in candidates:
            sym = cand["symbol"]
            existing = [p for p in active_swing if p["symbol"] == sym]
            if existing:
                continue

            setup = self.strategy.evaluate_setup(sym)
            if setup and setup.get("valid"):
                price = setup["price"]
                per_trade_cap = max_swing_desk_capital / 5.0
                qty = max(1, int(per_trade_cap / price))

                self.execution.buy_delivery(
                    symbol=sym,
                    qty=qty,
                    price=price,
                    stop_loss=setup["stop_loss"],
                    target=setup["target"]
                )
                self.db.log(
                    "INFO",
                    f"[Swing Desk] OPENED CNC DELIVERY: {sym} qty={qty} @ ₹{price:.2f} "
                    f"(Target: ₹{setup['target']:.2f}, SL: ₹{setup['stop_loss']:.2f}, R:R {setup['rr_ratio']}x)"
                )


def run_swing_standalone():
    """CLI entry point for running only the Swing Trading Desk."""
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
    runner = SwingDeskRunner(db, provider, cfg)

    print("==================================================")
    print("   Tradng-Ai PRO: STOCKS & SWING DESK (CNC)       ")
    print("   Exempt from 15:10 IST EOD (Multi-day Holding)  ")
    print("==================================================")
    while True:
        try:
            runner.run_cycle()
            time.sleep(15)  # Swing desk scans on a relaxed cycle
        except KeyboardInterrupt:
            print("\nSwing Desk stopped by user.")
            break
        except Exception as e:
            print(f"[Swing Desk Error]: {e}")
            time.sleep(15)


if __name__ == "__main__":
    run_swing_standalone()
