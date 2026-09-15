from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.ai_trader import AITrader

def candidate():
    return {"symbol":"TEST.NS","price":100,"score":85,"rsi":65,"atr":2,
            "rel_volume":1.8,"ret_5":.02,"ret_20":.05,"sector":"IT","news_bias":4}

def test_ai_can_use_positive_news():
    p=AITrader().propose(candidate(),"Strong bullish trend","Bullish")
    assert p["action"]=="BUY"
    assert p["risk_reward"] >= 1.5

def test_ai_short_has_upside_stop_direction():
    c=candidate(); c.update({"ret_5":-.03,"ret_20":-.05,"rsi":35,"news_bias":-4})
    p=AITrader().propose(c,"Strong bearish trend","Bearish")
    assert p["action"]=="SHORT"
    assert p["stop_loss"]>p["price"]>p["target"]
