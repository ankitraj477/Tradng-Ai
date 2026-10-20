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
        today_date = now.strftime("%Y-%m-%d")
        last_held_date = self.db.get_setting("last_swing_held_date", "")
        if today_date != last_held_date:
            self.db.increment_all_swing_days_held()
            self.db.set_setting("last_swing_held_date", today_date)

        closed = self.position_manager.manage()
        if closed > 0:
            self.db.log("INFO", f"[Swing Desk] Managed and closed {closed} swing delivery positions")

        # 1b. If market is open, fill any pending After-Market Orders (AMOs)
        self._fill_pending_amos()

        # 2. Check if auto trading is enabled
        if not self.db.is_auto_trading_enabled():
            return

        # 3. Market Regime Gate (Minervini Rule #1: General Market Direction Confirmation)
        market_state = self.db.market()
        regime = str(market_state.get("regime", "BULLISH")).upper()
        if "BEAR" in regime:
            self.db.log("INFO", f"[Swing Desk] General market regime is {regime}. New swing longs paused per Minervini Rule #1.")
            return

        # 4. Capital check for swing desk
        alloc = self.db.get_capital_allocation()
        swing_alloc_pct = alloc.get("swing", 40.0) / 100.0
        account = self.db.account()
        cash = float(account.get("cash", 0.0)) if account else 0.0
        starting = float(account.get("starting_capital", 100000.0)) if account else 100000.0
        max_swing_desk_capital = min(starting * swing_alloc_pct, cash)

        # Count active swing positions (max 3 concurrent swing holdings for focus)
        current_active = self.db.positions_by_product("SWING")
        if len(current_active) >= 3:
            self.db.log("INFO", f"[Swing Desk] Max concurrent swing holdings reached (3). Monitoring active trades.")
            return

        # 5. Scan for Stage 2 Trend Template & 20 EMA Pullback candidates
        from ..market_hours import market_open
        is_open = market_open()
        universe = get_universe_symbols()
        candidates = self.scanner.scan_stage2_candidates(universe[:40])

        for cand in candidates:
            # Re-check active swing count inside loop
            current_active = self.db.positions_by_product("SWING")
            if len(current_active) >= 3:
                break

            sym = cand["symbol"]
            existing = [p for p in current_active if p["symbol"] == sym]
            if existing:
                continue

            # Quality Filter: Minervini score must be >= 80
            if float(cand.get("score", 0)) < 80.0:
                continue

            setup = self.strategy.propose(cand)
            if not setup:
                continue
            setup["rr_ratio"] = setup.get("risk_reward", 2.5)

            price = float(setup["price"])
            per_trade_cap = max_swing_desk_capital / 3.0
            qty = int(per_trade_cap / price)
            if qty <= 0:
                continue
            if (qty * price) > cash * 0.30:  # Never risk more than 30% of cash on one swing trade
                qty = int((cash * 0.30) / price)
            if qty <= 0:
                continue

            # Record AI Research / Decision Stream on Dashboard
            self.db.add_decision({
                "symbol": sym,
                "action": "BUY",
                "confidence": cand.get("score", 82),
                "strategy": "Stage-2 20 EMA Pullback",
                "reason": (
                    f"Stage-2 leader setup: Price ₹{price:.2f} testing 20 EMA with volume dry-up. "
                    f"52w High Proximity: ₹{cand.get('high_52w', 0):.2f}. "
                    f"Target: ₹{setup['target']:.2f} (+{((setup['target']-price)/price*100):.1f}%), "
                    f"SL: ₹{setup['stop_loss']:.2f} (-{((price-setup['stop_loss'])/price*100):.1f}%), "
                    f"R:R = 1:{setup.get('rr_ratio', 2.5):.1f}"
                ),
                "risk_decision": "APPROVED" if is_open else "QUEUED_RESEARCH"
            })

            # When market is closed, DO NOT execute or place orders without market open!
            if not is_open:
                self.db.log(
                    "INFO",
                    f"[Swing Desk Research] Screened {sym}: Score={cand.get('score')}/100, "
                    f"R:R=1:{setup.get('rr_ratio', 2.5):.1f}. Published to Research Feed. (Market Closed: No orders placed)"
                )
                continue

            # Execute only when market is open
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

    def _fill_pending_amos(self):
        """When market is open, fill any pending After-Market Orders into active holdings."""
        from ..market_hours import market_open
        if not market_open():
            return
        pending = self.db.pending_orders()
        for o in pending:
            if o.get("product_type") == "SWING" and o.get("action") == "BUY":
                sym = o["symbol"]
                qty = int(o["qty"])
                fill_price = None
                if self.provider and hasattr(self.provider, "quote"):
                    try:
                        q = self.provider.quote(sym)
                        if q and "price" in q:
                            fill_price = float(q["price"])
                    except Exception:
                        fill_price = None
                if fill_price is None:
                    fill_price = float(o["price"])

                ok = self.execution.buy_delivery(sym, qty, fill_price, o.get("stop_loss"), o.get("target"), force_fill=True)
                if ok:
                    self.db.fill_order(o["id"], fill_price=fill_price)
                    self.db.log("INFO", f"[AMO FILLED] Market Open (09:15 IST): Executed AMO for {sym} x{qty} @ ₹{fill_price:.2f} into Holdings.")
                else:
                    self.db.cancel_order(o["id"], reason="Insufficient cash or execution failure at market open")
                    self.db.log("WARN", f"[AMO CANCELLED] Could not execute AMO for {sym} (insufficient capital).")


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
