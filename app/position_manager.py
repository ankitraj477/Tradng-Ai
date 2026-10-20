"""
Position Manager Module.

NOTE: This module provides backwards-compatibility and points to the dedicated
Intraday Position Manager located at:
    app.intraday.position_manager.IntradayPositionManager

Architecture Separation:
1. Intraday Desk (MIS):
   - app/intraday/position_manager.py (Strict 15:10 IST EOD square-off, Breakeven at +0.5R, Dynamic Trailing)
   - app/intraday/execution.py
   - app/intraday/orb_strategy.py
   - app/intraday/scanner.py
   - app/intraday/runner.py

2. Stocks / Swing Desk (CNC Delivery):
   - app/swing/position_manager.py (Exempt from 15:10 EOD, 3-20 days holding, dynamic multi-day runners)
   - app/swing/execution.py
   - app/swing/pullback_strategy.py
   - app/swing/scanner.py
   - app/swing/runner.py

3. Futures & Options Desk (F&O):
   - app/fno/position_manager.py (50% profit-taking exit rule, Thursday 15:15 IST expiry)
   - app/fno/execution.py
   - app/fno/iron_condor.py
   - app/fno/index_chain.py
   - app/fno/runner.py
"""

from .intraday.position_manager import IntradayPositionManager


class PositionManager(IntradayPositionManager):
    """Deterministic fast protection for Intraday MIS positions."""
    pass
