"""
Launcher for Intraday Trading Desk (MIS).
Can be run completely independently for debugging or isolated execution.
Usage: python run_intraday.py
"""

from app.intraday.runner import run_intraday_standalone

if __name__ == "__main__":
    run_intraday_standalone()
