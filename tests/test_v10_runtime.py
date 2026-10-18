import json
from pathlib import Path
import pandas as pd
import numpy as np
from app.config import load_config
from app.runtime import preflight
from app.universe import Universe
from app.engine import TradingEngine

class Provider:
    def __init__(self): self.universe=type('U',(),{'validate':lambda s,n:(True,500)})()

def test_live_preflight_requires_dependencies_and_universe_shape():
    cfg=load_config(); cfg['live_data']=True
    r=preflight(cfg,Provider())
    names={x['name'] for x in r['checks']}
    assert {'python_dependencies','database_parent','nifty500_universe','broker_execution'} <= names

def test_yfinance_intraday_lookback_is_60d():
    cfg = load_config()
    assert cfg['market']['history_period'] == '60d'

def test_engine_has_portfolio_selector(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "runtime_test.db"))
    e = TradingEngine(live=False)
    assert hasattr(e, 'selector')
    assert Path(e.db.path).resolve() == (tmp_path / "runtime_test.db").resolve()
    assert e.preflight['ok'] is True
