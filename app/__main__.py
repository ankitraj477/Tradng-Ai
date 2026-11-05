import argparse, threading, os
from .logger import setup_logging
from .engine import TradingEngine
from .dashboard import create_app

p = argparse.ArgumentParser()
p.add_argument("--live", action="store_true", help="use public market-data provider for paper trading")
p.add_argument("--log-level", default=None, choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="set logging level")
args = p.parse_args()

setup_logging(log_level=args.log_level)
engine = TradingEngine(live=args.live)
if os.getenv("REQUIRE_PREFLIGHT", "true").lower() == "true" and not engine.preflight["ok"]:
    print("STARTUP PREFLIGHT FAILED:")
    for check in engine.preflight["checks"]:
        if not check["ok"]: print(f"- {check['name']}: {check['details']}")
    raise SystemExit(2)
app=create_app(engine.db, engine.cfg, engine.provider)
threading.Thread(target=engine.run_forever,daemon=True).start()
app.run(host=os.getenv("APP_HOST", "127.0.0.1"), port=int(os.getenv("APP_PORT", "5000")), debug=False)
