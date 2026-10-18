import time
from app.data.manifest import DatasetManifest

def test_manifest_cycle_time_flat(tmp_path):
    manifest = DatasetManifest(tmp_path / "manifest.db")
    symbols = [f"SYM_{i}.NS" for i in range(10)]

    # Measure first 50 cycles
    t0 = time.perf_counter()
    for cycle in range(50):
        for s in symbols:
            manifest.record("yfinance", "ohlcv", s, "2026-01-01", f"2026-01-01 {cycle:02d}:00", 80)
    t_first_50 = time.perf_counter() - t0

    # Run intermediate cycles up to 450
    for cycle in range(50, 450):
        for s in symbols:
            manifest.record("yfinance", "ohlcv", s, "2026-01-01", f"2026-01-01 {cycle:02d}:00", 80)

    # Measure last 50 cycles (cycles 450 to 500)
    t1 = time.perf_counter()
    for cycle in range(450, 500):
        for s in symbols:
            manifest.record("yfinance", "ohlcv", s, "2026-01-01", f"2026-01-01 {cycle:02d}:00", 80)
    t_last_50 = time.perf_counter() - t1

    # Ratio of last 50 cycles to first 50 cycles should be near 1.0 (definitely < 3.0, unlike JSON rewrite which was 14x)
    assert t_last_50 < max(t_first_50 * 3.0, 0.5)

    records = manifest.records()
    assert len(records) == 10
    assert records[0]["source"] == "yfinance"
