"""Runtime diagnostics for safe paper trading."""

from pathlib import Path
import importlib.util
import os
import shutil


REQUIRED = (
    "flask",
    "pandas",
    "numpy",
    "yfinance",
    "feedparser",
    "requests",
)


def dependency_status():
    return {
        name: bool(importlib.util.find_spec(name))
        for name in REQUIRED
    }


def _cpp_scanner_available(cfg):
    if not cfg.get("use_cpp_scanner", False):
        return True, "disabled"

    configured = (
        cfg.get("cpp_scanner_path")
        or os.getenv("CPP_SCANNER_PATH")
    )

    candidates = []

    if configured:
        candidates.append(Path(configured))

    root = Path(__file__).resolve().parent.parent

    candidates.extend(
        [
            root / "cpp" / "scanner.exe",
            root / "cpp" / "scanner",
        ]
    )

    system_scanner = shutil.which("scanner")

    if system_scanner:
        candidates.append(Path(system_scanner))

    for candidate in candidates:
        if candidate.exists():
            return True, str(candidate)

    return False, "requested but compiled scanner was not found"


def preflight(cfg, provider=None):
    checks = []

    deps = dependency_status()

    checks.append(
        {
            "name": "python_dependencies",
            "ok": all(deps.values()),
            "details": deps,
        }
    )

    db_path = Path(
        cfg.get("database_path")
        or (
            Path(__file__).resolve().parent.parent
            / "data"
            / "trader.db"
        )
    )

    checks.append(
        {
            "name": "database_parent",
            "ok": db_path.parent.exists(),
            "details": str(db_path),
        }
    )

    if cfg.get("live_data"):
        try:
            if (
                provider is not None
                and hasattr(provider, "universe")
            ):
                ok, count = provider.universe.validate(450)
            else:
                ok, count = False, 0

            checks.append(
                {
                    "name": "nifty500_universe",
                    "ok": ok,
                    "details": (
                        f"{count} active constituents "
                        "(minimum 450)"
                    ),
                }
            )

        except Exception as exc:
            checks.append(
                {
                    "name": "nifty500_universe",
                    "ok": False,
                    "details": repr(exc),
                }
            )

    else:
        checks.append(
            {
                "name": "paper_mode",
                "ok": True,
                "details": (
                    "demo provider; "
                    "no broker execution"
                ),
            }
        )

    cpp_ok, cpp_details = _cpp_scanner_available(cfg)

    if cfg.get("use_cpp_scanner"):
        checks.append(
            {
                "name": "cpp_scanner",
                "ok": cpp_ok,
                "details": cpp_details,
            }
        )

    # Hard architecture guarantee:
    # this application contains no broker execution.
    checks.append(
        {
            "name": "broker_execution",
            "ok": True,
            "details": (
                "disabled by architecture; "
                "paper trading only"
            ),
        }
    )

    return {
        "ok": all(
            check["ok"]
            for check in checks
        ),
        "checks": checks,
    }