"""Run startup safety checks from any working directory.

Usage from the project root:
    python scripts/preflight.py

The script adds the project root to sys.path so ``app`` imports work even
when this file is launched directly. Missing third-party dependencies are
reported by the application preflight instead of being treated as an import
path failure.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from app.config import load_config
    from app.engine import TradingEngine
except ModuleNotFoundError as exc:
    print(f"[FAIL] Python dependency/import: {exc}")
    print("Install the project dependencies with: python -m pip install -r requirements.txt")
    raise SystemExit(2)

cfg = load_config()
engine = TradingEngine(live=cfg.get("live_data", False))
for check in engine.preflight["checks"]:
    mark = "PASS" if check["ok"] else "FAIL"
    print(f"[{mark}] {check['name']}: {check['details']}")

if not engine.preflight["ok"]:
    print("\nPreflight failed. Fix the reported checks before starting paper trading.")
    raise SystemExit(2)

print("\nPreflight passed. Runtime is ready for the selected mode.")
