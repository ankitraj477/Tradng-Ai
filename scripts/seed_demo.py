from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.engine import TradingEngine
e=TradingEngine(live=False)
for _ in range(3):
    e.cycle()
print("Demo cycles complete. Run: python -m app")
