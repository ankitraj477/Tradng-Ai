
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.accounting import portfolio_metrics

def test_canonical_short_equity():
    a={"cash":750}
    p=[{"side":"SHORT","qty":1,"entry_price":100,"current_price":90}]
    m=portfolio_metrics(a,p,.25)
    assert m["equity"]==760
    assert m["reserved_margin"]==25
    assert m["gross_exposure"]==90

def test_canonical_long_and_short_metrics():
    a={"cash":500}
    p=[
      {"side":"LONG","qty":2,"entry_price":100,"current_price":110},
      {"side":"SHORT","qty":1,"entry_price":100,"current_price":90},
    ]
    m=portfolio_metrics(a,p,.25)
    assert m["equity"]==730
    assert m["gross_exposure"]==310
    assert m["net_exposure"]==130
