"""
Cross-platform safety test runner for Tradng-Ai hooks.
Detects virtualenv Python on Windows (.venv\\Scripts\\python.exe) and Linux (.venv/bin/python).
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def get_venv_python():
    win_py = ROOT / ".venv" / "Scripts" / "python.exe"
    linux_py = ROOT / ".venv" / "bin" / "python"
    if win_py.is_file():
        return str(win_py)
    if linux_py.is_file():
        return str(linux_py)
    return sys.executable


def main():
    py_bin = get_venv_python()
    cmd = [
        py_bin,
        "-m",
        "pytest",
        "tests/test_audit_security_and_invariants.py",
        "tests/test_costs.py",
        "-q",
    ]
    res = subprocess.run(cmd, cwd=str(ROOT))
    sys.exit(res.returncode)


if __name__ == "__main__":
    main()
