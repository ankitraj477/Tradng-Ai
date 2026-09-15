from app.db import DB
from app.accounting import portfolio_metrics

def test_dashboard_source_of_truth_metrics_match_canonical_accounting():
    db=DB(':memory:'); db.ensure_account(1000,100000)
    with db.conn() as c:
        c.execute("INSERT INTO positions(symbol,side,qty,entry_price,current_price,stop_loss,target,strategy,confidence,opened_at,sector) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  ('TEST','SHORT',2,100,90,110,80,'demo',0.8,'2026-09-14T07:00:00+00:00','IT'))
        c.execute("UPDATE account SET cash=1000")
    m=portfolio_metrics(db.account(),db.positions(),0.25)
    assert m['reserved_margin']==50.0
    assert m['short_notional']==180.0
    assert m['short_unrealized']==20.0
    assert m['equity']==1020.0
    assert m['available_cash']==950.0
