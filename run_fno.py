"""
Launcher for Futures & Options Desk (F&O Defined-Risk Spreads).
Can be run completely independently for debugging or isolated execution.
Usage: python run_fno.py
"""

from app.fno.runner import run_fno_standalone

if __name__ == "__main__":
    run_fno_standalone()
