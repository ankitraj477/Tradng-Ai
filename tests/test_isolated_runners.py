import pytest
from app.db import DB
from app.data.demo_provider import DemoProvider
from app.intraday.runner import IntradayDeskRunner
from app.swing.runner import SwingDeskRunner
from app.fno.runner import FnoDeskRunner
import run_intraday
import run_swing
import run_fno
import run_dashboard


@pytest.fixture
def isolated_env(tmp_path):
    db_file = tmp_path / "isolated_desk.db"
    db = DB(str(db_file))
    db.ensure_account(100000.0, 150000.0)
    provider = DemoProvider()
    cfg = {
        "capital": {"starting": 100000.0, "target": 150000.0},
        "execution": {"trailing_stop_atr": 1.5, "max_hold_minutes": 390},
        "risk": {"max_positions": 5}
    }
    return db, provider, cfg


def test_intraday_runner_cycle(isolated_env):
    db, provider, cfg = isolated_env
    runner = IntradayDeskRunner(db, provider, cfg)
    # Execute a cycle - must run without errors
    runner.run_cycle()
    assert runner.position_manager is not None
    assert runner.strategy is not None


def test_swing_runner_cycle(isolated_env):
    db, provider, cfg = isolated_env
    runner = SwingDeskRunner(db, provider, cfg)
    runner.run_cycle()
    assert runner.position_manager is not None
    assert runner.scanner is not None


def test_fno_runner_cycle(isolated_env):
    db, provider, cfg = isolated_env
    runner = FnoDeskRunner(db, provider, cfg)
    runner.run_cycle()
    assert runner.position_manager is not None
    assert runner.strategy is not None


def test_standalone_launchers_structure():
    assert callable(run_intraday.run_intraday_standalone)
    assert callable(run_swing.run_swing_standalone)
    assert callable(run_fno.run_fno_standalone)


def test_unified_trading_engine_runs_all_desks_together(isolated_env):
    db, provider, cfg = isolated_env
    from app.engine import TradingEngine
    engine = TradingEngine(cfg=cfg, db=db, provider=provider)
    assert hasattr(engine, "intraday_desk")
    assert hasattr(engine, "swing_desk")
    assert hasattr(engine, "fno_desk")

    # Run unified cycle - triggers all 3 desks together in a single call
    engine.cycle()
    assert engine.intraday_desk is not None
    assert engine.swing_desk is not None
    assert engine.fno_desk is not None
