from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.ai_trader import AITrader

def bearish_candidate():
    return {'symbol':'BEAR.NS','price':100,'score':85,'rsi':32,'atr':2,
            'rel_volume':1.8,'ret_5':-.03,'ret_20':-.06,'sector':'IT','news_bias':-4}

def test_short_pipeline_signal():
    p=AITrader().propose(bearish_candidate(),'Strong bearish trend','Bearish')
    assert p['action']=='SHORT'
    assert p['stop_loss'] > p['price'] > p['target']


def test_scanner_no_long_only_cash_filter():
    src=Path(__file__).resolve().parents[1].joinpath('app/scanner.py').read_text()
    assert 'q["price"] > cash: continue' not in src
