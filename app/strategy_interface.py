"""
Institutional Strategy Interface and Standard Protocol.
Defines the uniform contract for all trading strategies across F&O, Intraday, and Swing desks.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List


class BaseDeskStrategy(ABC):
    """
    Abstract Base Class for all multi-desk strategies.
    Enforces suitability scoring, risk metadata, and structured proposals.
    """
    def __init__(self, name: str, desk: str, supported_regimes: Optional[List[str]] = None):
        self.name = name
        self.desk = desk.upper()  # 'FNO', 'INTRADAY', 'SWING'
        self.supported_regimes = supported_regimes or ["All"]

    @abstractmethod
    def evaluate_market_fitness(self, context: Dict[str, Any]) -> float:
        """
        Evaluate the strategy's suitability for current market conditions.
        Returns a score between 0.0 (unfit) and 1.0 (optimal fit).
        
        Context typically contains:
        - 'regime': str (e.g. 'Bullish Trending', 'Bearish Trending', 'Consolidation', 'Volatile')
        - 'adx': float (trend strength, 0-100)
        - 'pcr': float (put-call ratio for F&O)
        - 'iv_percentile': float (0-100)
        - 'time_of_day': str or time
        - 'volume_ratio': float
        """
        pass

    @abstractmethod
    def propose(self, target: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Generate a trade proposal conforming to institutional standards.
        Returns None if no trade entry criteria are met.
        """
        pass

