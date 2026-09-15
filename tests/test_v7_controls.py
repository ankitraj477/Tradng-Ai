from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.ai_trader import AITrader
def test_long_protection_levels():
 c={"symbol":"A","price":100,"score":85,"rsi":65,"atr":2,"rel_volume":1.8,"ret_5":.02,"ret_20":.05,"news_bias":2}; p=AITrader().propose(c,"Strong bullish trend","Bullish"); assert p["action"]=="BUY" and p["stop_loss"]<100<p["target"]
def test_short_protection_levels():
 c={"symbol":"A","price":100,"score":85,"rsi":32,"atr":2,"rel_volume":1.8,"ret_5":-.03,"ret_20":-.06,"news_bias":-4}; p=AITrader().propose(c,"Strong bearish trend","Bearish"); assert p["action"]=="SHORT" and p["stop_loss"]>100>p["target"]
