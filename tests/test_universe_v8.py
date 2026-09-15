from pathlib import Path
from app.universe import Universe

def test_universe_validation_rejects_starter_universe():
    u=Universe(Path(__file__).resolve().parents[1]/'data'/'nifty500.csv')
    u.load()
    ok,count=u.validate(450)
    assert not ok and count < 450
