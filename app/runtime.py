"""Startup/runtime diagnostics for safe paper-trading operation."""
from pathlib import Path
import importlib.util

REQUIRED = ("flask", "pandas", "numpy", "yfinance", "feedparser", "requests")

def dependency_status():
    return {name: bool(importlib.util.find_spec(name)) for name in REQUIRED}

def preflight(cfg, provider=None):
    checks = []
    deps = dependency_status()
    checks.append({"name":"python_dependencies","ok":all(deps.values()),"details":deps})
    db_path = Path(__file__).resolve().parent.parent / "data" / "trader.db"
    checks.append({"name":"database_parent","ok":db_path.parent.exists() or db_path.parent.parent.exists(),"details":str(db_path)})
    if cfg.get("live_data"):
        try:
            ok,count = provider.universe.validate(450) if provider and hasattr(provider,"universe") else (False,0)
            checks.append({"name":"nifty500_universe","ok":ok,"details":f"{count} active constituents (minimum 450)"})
        except Exception as e:
            checks.append({"name":"nifty500_universe","ok":False,"details":repr(e)})
    else:
        checks.append({"name":"paper_mode","ok":True,"details":"demo provider; no broker execution"})
    checks.append({"name":"broker_execution","ok":True,"details":"disabled by architecture"})
    return {"ok":all(x["ok"] for x in checks),"checks":checks}
