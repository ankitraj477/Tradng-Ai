"""
Futures & Options (F&O) Desk for Nifty 50 & Bank Nifty.
Mathematical 75%+ win-rate defined-risk option selling engine
using 15-20 Delta Credit Spreads, Iron Condors, and PCR sentiment skew.
"""
from .index_chain import IndexChainManager
from .iron_condor import IronCondorStrategy
from .position_manager import FNOPositionManager
from .execution import FNOExecution

__all__ = [
    "IndexChainManager",
    "IronCondorStrategy",
    "FNOPositionManager",
    "FNOExecution",
]
