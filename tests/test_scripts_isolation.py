import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_scripts_refuse_default_db():
    default_db = ROOT / "data" / "trader.db"
    for script in ["test_trade.py", "test_10_trades.py", "test_profit_trades.py"]:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["DATABASE_PATH"] = str(default_db)
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / script)],
            env=env,
            capture_output=True,
            text=True,
        )
        assert proc.returncode != 0
        assert "Refusing to run on default trader.db" in proc.stderr or "Refusing to run on default trader.db" in proc.stdout

def test_scripts_leave_default_db_unchanged():
    default_db = ROOT / "data" / "trader.db"
    assert default_db.exists()
    h_before = hashlib.sha256(default_db.read_bytes()).hexdigest()

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "test_trade.py")],
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    h_after = hashlib.sha256(default_db.read_bytes()).hexdigest()
    assert h_before == h_after
