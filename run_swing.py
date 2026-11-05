"""
Launcher for Stocks / Swing Trading Desk (CNC Cash Delivery).
Can be run completely independently for debugging or isolated execution.
Usage: python run_swing.py
"""

from app.swing.runner import run_swing_standalone

if __name__ == "__main__":
    run_swing_standalone()
