"""
Tradng-Ai Unified Multi-Desk Trading Platform.

Triggers all desks together:
1. Desk 1: Intraday Trading Desk (MIS)
2. Desk 2: Stocks / Swing Trading Desk (CNC Delivery)
3. Desk 3: Futures & Options Desk (F&O Spreads)
4. Dashboard: Real-Time 4-Desk Web UI at http://127.0.0.1:5000
"""

import argparse
import os
import threading
from app.logger import setup_logging
from app.engine import TradingEngine
from app.dashboard import create_app


def main():
    p = argparse.ArgumentParser(description="Tradng-Ai Unified Multi-Desk Engine")
    p.add_argument("--live", action="store_true", help="use live market data provider")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    p.add_argument("--port", default=int(os.getenv("APP_PORT", "5000")), type=int)
    args = p.parse_args()

    setup_logging(log_level=args.log_level)
    print("=" * 60)
    print("   TRADNG-AI PRO v2.5: UNIFIED MULTI-DESK TRADING ENGINE    ")
    print("   [1] Intraday Desk (MIS)           -> ACTIVE        ")
    print("   [2] Stocks / Swing Desk (CNC)     -> ACTIVE        ")
    print("   [3] Futures & Options Desk (F&O)  -> ACTIVE        ")
    print("   [4] 4-Section Dashboard UI        -> http://127.0.0.1:5000")
    print("=" * 60)

    import sys
    from app.ops.instance_lock import SingleInstanceLock
    lock = SingleInstanceLock()
    if not lock.acquire():
        print("\n[WARNING] Another Tradng-Ai engine is already running. Exiting duplicate instance to protect database.")
        sys.exit(0)

    engine = TradingEngine(live=args.live)
    # Ensure all desks are active for unified multi-desk trading
    engine.cfg.setdefault("desks", {})
    engine.cfg["desks"]["enabled"] = True
    engine.cfg["desks"]["swing"] = True
    engine.cfg["desks"]["fno"] = True
    engine.reload_config(engine.cfg)

    app = create_app(engine.db, engine.cfg, engine.provider)

    # Trigger engine loop in background (runs Intraday, Swing, F&O simultaneously)
    engine_thread = threading.Thread(target=engine.run_forever, daemon=True)
    engine_thread.start()

    # Serve dashboard
    try:
        app.run(host=os.getenv("APP_HOST", "0.0.0.0"), port=args.port, debug=False)

    except OSError as e:
        print(f"\n[WARNING] Port {args.port} is already in use or unavailable: {e}")
        print(f"Trading engine continues running in background. Specify a different port with --port <number>.\n")
        engine_thread.join()



if __name__ == "__main__":
    main()
