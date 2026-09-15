from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.ai_trader import AITrader

def test_bearish_proposal_is_short():
    c={'symbol':'X','price':100,'score':80,'rsi':30,'atr':2,'rel_volume':2,'ret_5':-0.03,'ret_20':-0.05,'volatility':0.02,'sector':'IT'}
    p=AITrader().propose(c,'Bearish')
    assert p['action']=='SHORT'
    assert p['stop_loss']>p['price'] and p['target']<p['price']
