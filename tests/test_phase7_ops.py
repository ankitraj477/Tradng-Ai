import time
import threading
import numpy as np
import pandas as pd
import pytest

from app.ops.alerts import AlertManager, MemoryAlertSink
from app.ops.retrainer import OfflineRetrainer
from app.ops.champion_challenger import ChampionChallengerManager
from app.ops.protection_worker import IsolatedProtectionWorker


def test_alert_manager_and_throttling():
    sink = MemoryAlertSink()
    manager = AlertManager(sinks=[sink], throttle_seconds=2)

    # 1. Emit outage alert
    fired1 = manager.emit("CRITICAL", "DATA_OUTAGE", "NSE feed timeout for 15 minutes", {"symbol": "NIFTY50"})
    assert fired1 is True
    assert len(sink.alerts) == 1
    a1 = sink.alerts[0]
    assert a1["level"] == "CRITICAL"
    assert a1["category"] == "DATA_OUTAGE"
    assert "timeout" in a1["message"]
    assert a1["details"]["symbol"] == "NIFTY50"

    # 2. Duplicate alert within throttle window should be throttled
    fired2 = manager.emit("CRITICAL", "DATA_OUTAGE", "Repeated timeout")
    assert fired2 is False
    assert len(sink.alerts) == 1

    # 3. Different category alert should NOT be throttled
    fired3 = manager.emit("CRITICAL", "KILL_SWITCH", "Strategy drawdown breached threshold")
    assert fired3 is True
    assert len(sink.alerts) == 2
    assert sink.alerts[1]["category"] == "KILL_SWITCH"

    # 4. Drawdown alert
    fired4 = manager.emit("WARN", "DRAWDOWN", "Account drawdown at -4.2%")
    assert fired4 is True
    assert len(sink.alerts) == 3


def test_offline_retrainer_with_candidate_log():
    rng = np.random.default_rng(42)
    n = 60
    # Generate synthetic candidate log with features and forward return
    df = pd.DataFrame({
        "rsi": rng.uniform(20, 80, n),
        "rel_volume": rng.uniform(0.5, 3.0, n),
        "volatility": rng.uniform(0.01, 0.05, n),
        "ret_5": rng.uniform(-0.05, 0.05, n),
        "ret_20": rng.uniform(-0.10, 0.10, n),
        "bull_score": rng.uniform(0, 10, n),
        "bear_score": rng.uniform(0, 10, n),
        "forward_ret_5d": rng.normal(0.005, 0.02, n)
    })

    retrainer = OfflineRetrainer(target_horizon="forward_ret_5d", cost_hurdle=0.0012)
    res = retrainer.retrain(df)

    assert res["success"] is True
    assert res["samples"] == 60
    assert "cv_accuracy" in res
    assert res["cv_accuracy"] >= 0.0
    assert "feature_importances" in res
    assert len(res["feature_importances"]) == 7
    assert res["model"] is not None

    # Test insufficient data threshold (<20 rows)
    small_df = df.iloc[:10]
    res_small = retrainer.retrain(small_df)
    assert res_small["success"] is False
    assert "Insufficient" in res_small["reason"]


class MockModel:
    def __init__(self, take_prob=0.8, mult=1.0):
        self.take_prob = take_prob
        self.mult = mult

    def predict_decision(self, features):
        return {
            "take": True,
            "size_multiplier": self.mult
        }


def test_champion_challenger_governance():
    champ = MockModel(mult=0.5)
    chall = MockModel(mult=1.0)

    mgr = ChampionChallengerManager(champion_model=champ, challenger_model=chall, min_evaluation_trades=20)

    # 1. Under-threshold evaluation returns unpromoted
    for _ in range(10):
        mgr.record_decision_outcomes(features={}, realized_return=0.02, cost_pct=0.0012)
    eval_under = mgr.evaluate_promotion()
    assert eval_under["promoted"] is False
    assert "Insufficient" in eval_under["reason"]

    # 2. Add remaining trades where positive return favors larger sizing challenger
    for _ in range(15):
        mgr.record_decision_outcomes(features={}, realized_return=0.03, cost_pct=0.0012)

    eval_res = mgr.evaluate_promotion()
    assert eval_res["promoted"] is True
    assert mgr.champion == chall  # Challenger promoted to Champion
    assert mgr.challenger is None

    # 3. Test inferior challenger is rejected
    inferior_chall = MockModel(mult=2.0)
    mgr.set_challenger(inferior_chall)
    # Simulate adverse trades where larger multiplier loses more
    for _ in range(25):
        mgr.record_decision_outcomes(features={}, realized_return=-0.02, cost_pct=0.0012)
    eval_inferior = mgr.evaluate_promotion()
    assert eval_inferior["promoted"] is False
    assert "failed to outperform" in eval_inferior["reason"]


class MockPositionManager:
    def __init__(self):
        self.managed_count = 0
        self.lock = threading.Lock()

    def manage(self):
        with self.lock:
            self.managed_count += 1


def test_protection_worker_isolation_when_scanner_fails():
    pos_mgr = MockPositionManager()
    worker = IsolatedProtectionWorker(position_manager=pos_mgr, interval_seconds=0.02)
    worker.start()

    time.sleep(0.06)
    assert worker.is_alive() is True
    initial_cycles = worker.cycle_count
    assert initial_cycles > 0

    # Simulate an external Scanner/News thread that crashes with an unhandled exception
    scanner_crashed = threading.Event()

    def buggy_scanner():
        try:
            time.sleep(0.03)
            raise RuntimeError("Simulated scanner network timeout and fatal crash!")
        except Exception:
            scanner_crashed.set()

    scanner_thread = threading.Thread(target=buggy_scanner, daemon=True)
    scanner_thread.start()
    scanner_thread.join(timeout=1.0)

    assert scanner_crashed.is_set() is True
    assert scanner_thread.is_alive() is False

    # Verify that protection worker is STILL alive and continuing execution
    time.sleep(0.08)
    assert worker.is_alive() is True
    assert worker.cycle_count > initial_cycles
    assert pos_mgr.managed_count > initial_cycles

    worker.stop()
    assert worker.is_alive() is False
