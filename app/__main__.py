import argparse, threading, os
from .engine import TradingEngine
from .dashboard import create_app

p=argparse.ArgumentParser()
p.add_argument("--live",action="store_true",help="use public market-data provider for paper trading")
args=p.parse_args()

engine=TradingEngine(live=args.live)
app=create_app(engine.db)
threading.Thread(target=engine.run_forever,daemon=True).start()
app.run(host=os.getenv("APP_HOST","0.0.0.0"),port=int(os.getenv("APP_PORT","5000")),debug=False)
