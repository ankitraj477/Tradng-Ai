"""
Shared engine package (v2).
Provides:
- Proposal and Fill dataclasses
- Pure simulate_fill()
- Multi-sleeve Ledger with exact accounting invariants
- PortfolioRiskManager with cross-sleeve ownership and drawdown ladder
"""

from .simulate import Proposal, simulate_fill
from .ledger import Ledger, Position, Fill
from .risk import PortfolioRiskManager

__all__ = [
    "Proposal",
    "simulate_fill",
    "Ledger",
    "Position",
    "Fill",
    "PortfolioRiskManager",
]
