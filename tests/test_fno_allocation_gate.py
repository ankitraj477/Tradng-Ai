import pytest
from app.fno.runner import FnoDeskRunner

def test_fno_runner_respects_zero_allocation():
    class DummyDB:
        def is_auto_trading_enabled(self):
            return True
        def get_capital_allocation(self):
            return {"intraday": 100.0, "swing": 0.0, "fno": 0.0}
        def positions_by_product(self, prod):
            return []
        def pending_orders(self):
            return []
        def log(self, *args, **kwargs):
            pass

    from types import SimpleNamespace
    runner = FnoDeskRunner.__new__(FnoDeskRunner)
    runner.db = DummyDB()
    runner.cfg = {}
    runner.position_manager = SimpleNamespace(manage=lambda dt: 0)
    
    # Should exit immediately without evaluating spreads
    runner._run_iteration(is_fast_tick=False)
    runner._fill_pending_amos()
