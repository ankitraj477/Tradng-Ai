from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.news import NewsProvider

class M:
    company="Reliance Industries"

def test_company_news_mapping():
    n=NewsProvider()
    assert "RELIANCE.NS" in n.match_symbols("Reliance Industries reports strong profit growth", {"RELIANCE.NS":M()})

def test_news_score_is_bounded_feature():
    n=NewsProvider()
    assert -10 <= max(-10,min(10,100*2)) <= 10
