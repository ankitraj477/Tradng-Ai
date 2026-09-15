
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.accounting import portfolio_metrics

def test_accounting_never_confuses_margin_with_equity():
    a={"cash":1000}
    p=[{"side":"SHORT","qty":10,"entry_price":100,"current_price":95}]
    m=portfolio_metrics(a,p,.25)
    assert m["equity"]==1050
    assert m["reserved_margin"]==250
    assert m["available_cash"]==750
