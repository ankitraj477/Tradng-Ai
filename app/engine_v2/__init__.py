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
from .paper_forward import (
    DataOutageGuard,
    PaperForwardRunner,
    run_paper_forward_simulation,
    compute_drift_metrics,
    generate_paper_forward_report,
)

__all__ = [
    "Proposal",
    "simulate_fill",
    "Ledger",
    "Position",
    "Fill",
    "PortfolioRiskManager",
    "DataOutageGuard",
    "PaperForwardRunner",
    "run_paper_forward_simulation",
    "compute_drift_metrics",
    "generate_paper_forward_report",
]
