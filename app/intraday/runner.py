"""
Standalone Intraday Trading Desk Runner.
Runs completely independent of Swing and F&O.
"""

import time
from datetime import datetime
from ..market_hours import now_ist, market_open
from ..universe import get_universe_symbols
from .timing import IntradayTimingManager
from .position_manager import IntradayPositionManager
from .execution import IntradayExecution
from .orb_strategy import ORBDeskStrategy
from .scanner import IntradayScanner


class IntradayDeskRunner:
    def __init__(self, db, provider, cfg=None):
        self.db = db
        self.provider = provider
        self.cfg = cfg or {}
        self.timing = IntradayTimingManager()
        self.execution = IntradayExecution(db, self.cfg)
        self.position_manager = IntradayPositionManager(db, self.execution, provider, self.cfg)
        self.strategy = ORBDeskStrategy(provider, self.cfg)
        self.scanner = IntradayScanner(provider, self.cfg)

    def run_cycle(self):
        """Execute one complete cycle for the Intraday desk."""
        now = now_ist()
        self.db.log("INFO", f"[Intraday Desk] Starting cycle at {now.strftime('%H:%M:%S')} IST")

        # 1. Manage active intraday positions (stops, targets, 15:10 IST square-off)
        closed = self.position_manager.manage(dt=now)
        if closed > 0:
            self.db.log("INFO", f"[Intraday Desk] Managed and closed {closed} intraday positions")

        # 2. Check market hours and entry window (09:30 - 14:45 IST)
        enforce_hours = self.cfg.get("execution", {}).get("enforce_market_hours", True)
        if enforce_hours and (not market_open(now) or not self.timing.can_enter(now)):
            self.db.log("INFO", f"[Intraday Desk] Outside intraday entry window. Monitoring only.")
            return

        if not self.db.is_auto_trading_enabled():
            return

        # 3. Check max open intraday positions
        current_intraday = [p for p in self.db.positions() if p.get("product_type", "INTRADAY") == "INTRADAY"]
        max_intra_positions = int(self.cfg.get("market", {}).get("max_open_positions", 5))
        if len(current_intraday) >= max_intra_positions:
            self.db.log("INFO", f"[Intraday Desk] Max open positions reached ({len(current_intraday)}/{max_intra_positions}). Monitoring active trades.")
            return

        # 4. Automated Market Regime Evaluation: Bot dynamically decides trade direction
        market_info = self.db.market()
        current_regime = str(market_info.get("regime", "Neutral"))
        current_regime_lower = current_regime.lower()

        # Shorting policy: Allowed only if config permits AND regime is confirmed strongly bearish
        allow_shorts_cfg = self.cfg.get("allow_shorts", "auto")
        regime_allows_short = any(k in current_regime_lower for k in ("strong bearish", "bearish trend", "downtrend"))
        can_short = (allow_shorts_cfg not in (False, "false")) and regime_allows_short

        # Buying policy: Suppress long entries during an active market crash
        can_buy = "strong bearish" not in current_regime_lower

        # 5. Scan candidates & evaluate ORB signals
        alloc = self.db.get_capital_allocation()
        intra_alloc_pct = alloc.get("intraday", 40.0) / 100.0
        min_notional = float(self.cfg.get("risk", {}).get("min_trade_notional", 5000.0))

        universe = get_universe_symbols()
        candidates = self.scanner.scan_opening_candidates(universe[:30])
        for cand in candidates:
            if len(current_intraday) >= max_intra_positions:
                break

            sym = cand["symbol"]
            # Skip if already held in intraday
            existing = [p for p in current_intraday if p["symbol"] == sym]
            if existing:
                continue

            sig = self.strategy.evaluate(sym, market_regime=current_regime)
            if sig and sig.action in ("BUY", "SHORT"):
                # Automated Directional Gates
                if sig.action == "SHORT" and not can_short:
                    reason = "disabled in config" if allow_shorts_cfg in (False, "false") else f"market regime '{current_regime}' is not bearish"
                    self.db.log("INFO", f"[Intraday Desk] AUTOMATED REGIME GATE: Blocked SHORT on {sym} ({reason}). Preserving capital.")
                    continue

                if sig.action == "BUY" and not can_buy:
                    self.db.log("INFO", f"[Intraday Desk] AUTOMATED REGIME GATE: Blocked BUY on {sym} during {current_regime} crash.")
                    continue

                quote = self.provider.quote(sym)
                price = float(quote.get("price", cand["price"]))
                if price <= 0:
                    continue

                # Sized capital allocation
                account = self.db.account()
                starting = account.get("starting_capital", 100000.0) if account else 100000.0
                max_trade_cap = (starting * intra_alloc_pct) / 5.0

                qty = int(max_trade_cap / price)
                if qty <= 0:
                    self.db.log("INFO", f"[Intraday Desk] SIZING GATE: Skipped {sym} (price ₹{price:.2f} exceeds per-trade allocation ₹{max_trade_cap:.2f})")
                    continue

                trade_notional = qty * price
                if trade_notional < min_notional:
                    self.db.log("INFO", f"[Intraday Desk] SIZING GATE: Skipped {sym} (notional ₹{trade_notional:.2f} < minimum ₹{min_notional:.2f})")
                    continue

                if sig.action == "BUY":
                    self.execution.open_long(
                        sym, qty, price,
                        sig.stop_loss or (price * 0.99),
                        sig.target or (price * 1.02),
                        sig.atr or (price * 0.01)
                    )
                    self.db.log("INFO", f"[Intraday Desk] ENTERED LONG {sym} qty={qty} at {price:.2f} (notional: ₹{trade_notional:.2f})")
                    current_intraday.append({"symbol": sym})
                elif sig.action == "SHORT":
                    self.execution.open_short(
                        sym, qty, price,
                        sig.stop_loss or (price * 1.01),
                        sig.target or (price * 0.98),
                        sig.atr or (price * 0.01)
                    )
                    self.db.log("INFO", f"[Intraday Desk] ENTERED SHORT {sym} qty={qty} at {price:.2f} (notional: ₹{trade_notional:.2f})")
                    current_intraday.append({"symbol": sym})


def run_intraday_standalone():
    """CLI entry point for running only the Intraday Trading Desk."""
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
    runner = IntradayDeskRunner(db, provider, cfg)

    print("==================================================")
    print("   Tradng-Ai PRO: INTRADAY TRADING DESK (MIS)    ")
    print("   15:10 IST EOD Auto Square-Off Active           ")
    print("==================================================")
    while True:
        try:
            runner.run_cycle()
            time.sleep(5)
        except KeyboardInterrupt:
            print("\nIntraday Desk stopped by user.")
            break
        except Exception as e:
            print(f"[Intraday Desk Error]: {e}")
            time.sleep(5)


if __name__ == "__main__":
    run_intraday_standalone()
