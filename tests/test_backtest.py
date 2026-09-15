import pandas as pd, numpy as np
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.backtest import Backtester

def test_backtest_returns_metrics():
    n=500
    rng=np.random.default_rng(1)
    close=100*np.exp(np.cumsum(rng.normal(.0003,.01,n)))
    df=pd.DataFrame({"Open":close,"High":close*1.002,"Low":close*.998,"Close":close,
                     "Volume":rng.integers(10000,100000,n)})
    r=Backtester().run(df)
    assert "max_drawdown_pct" in r
    assert r["start"]==1000
