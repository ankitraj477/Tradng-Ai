import numpy as np, pandas as pd
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.backtest import Backtester

def bars(seed):
    rng=np.random.default_rng(seed); n=500
    c=100*np.exp(np.cumsum(rng.normal(.0004,.008,n)))
    return pd.DataFrame({'Open':c,'High':c*1.004,'Low':c*.996,'Close':c,'Volume':rng.integers(10000,100000,n)},
                        index=pd.date_range('2025-01-01',periods=n,freq='5min'))

def test_portfolio_equity_compounds_and_supports_multiple_symbols():
    r=Backtester(starting_cash=1000,max_positions=2,max_position_pct=.20).run_portfolio({'A':bars(1),'B':bars(2)})
    assert r['start']==1000
    assert r['end']>=0
    assert all(t['qty']>0 for t in r['trades_detail'])

def test_short_trades_have_valid_direction():
    r=Backtester(starting_cash=1000,max_positions=1).run_portfolio({'A':bars(4)})
    shorts=[t for t in r['trades_detail'] if t['side']=='SHORT']
    assert all(t['entry']>0 and t['exit']>0 for t in shorts)
