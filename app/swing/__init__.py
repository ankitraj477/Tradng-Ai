"""
Swing Trading & Positional Delivery Desk (CNC).
Multi-day holding strategy based on Mark Minervini's Stage-2 Trend Filter
and 20 EMA pullback with volume dry-up confirmation.
"""
from .scanner import SwingScanner
from .pullback_strategy import SwingPullbackStrategy
from .position_manager import SwingPositionManager
from .execution import SwingExecution

__all__ = [
    "SwingScanner",
    "SwingPullbackStrategy",
    "SwingPositionManager",
    "SwingExecution",
]
