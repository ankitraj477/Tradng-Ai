import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.data.demo_provider import DemoProvider
from app.backtest import Backtester
from app.benchmarks import buy_hold

p=DemoProvider()
df=p.history("RELIANCE.NS",period="3mo",interval="5m")
bt=Backtester(1000)
result=bt.run(df,"RELIANCE.NS")
print("AI PAPER BACKTEST")
for k,v in result.items():
    if k!="trades_detail": print(f"{k}: {v}")
print("BUY & HOLD BASELINE:",buy_hold(df))
