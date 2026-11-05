"""
Institutional Strategy Router and Meta-Decision Dispatcher.
Dynamically orchestrates and selects optimal trading strategies across F&O, Intraday, and Swing
based on real-time market regimes, ADX trend strength, PCR sentiment, and time-of-day dynamics.
"""
from typing import Dict, Any, Optional, List
from .strategy_interface import BaseDeskStrategy
from .fno.iron_condor import IronCondorStrategy
from .fno.debit_spreads import DirectionalDebitSpreadStrategy
from .intraday.orb_strategy import OpeningRangeBreakoutStrategy
from .intraday.vwap_pullback import VWAPPullbackStrategy
from .swing.pullback_strategy import SwingPullbackStrategy
from .swing.momentum_breakout import SwingMomentumBreakoutStrategy


class DeskStrategyRouter:
    """
    Central Meta-Decision Engine that selects which strategy to deploy
    for each trading desk (F&O, Intraday, Swing) based on market state.
    """
    def __init__(self, db=None, cfg=None):
        self.db = db
        self.cfg = cfg or {}
        self.strategies: Dict[str, List[BaseDeskStrategy]] = {
            "FNO": [],
            "INTRADAY": [],
            "SWING": []
        }
        self._init_default_strategies()

    def _init_default_strategies(self):
        """Register institutional strategies for each desk."""
        # F&O Strategies
        self.register_strategy(IronCondorStrategy(cfg=self.cfg))
        self.register_strategy(DirectionalDebitSpreadStrategy(cfg=self.cfg))

        # Intraday Strategies
        self.register_strategy(OpeningRangeBreakoutStrategy())
        self.register_strategy(VWAPPullbackStrategy())

        # Swing Strategies
        self.register_strategy(SwingPullbackStrategy())
        self.register_strategy(SwingMomentumBreakoutStrategy())

    def register_strategy(self, strategy: BaseDeskStrategy):
        desk = strategy.desk.upper()
        if desk in self.strategies:
            self.strategies[desk].append(strategy)

    def select_best_strategy(self, desk: str, context: Dict[str, Any]) -> Optional[BaseDeskStrategy]:
        """
        Calculates fitness score across all strategies on the desk and
        returns the highest-scoring strategy matching the market context.
        """
        desk = desk.upper()
        available = self.strategies.get(desk, [])
        if not available:
            return None

        scored = []
        for strat in available:
            fitness = strat.evaluate_market_fitness(context)
            scored.append((fitness, strat))

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_strat = scored[0]

        if self.db and hasattr(self.db, "log"):
            self.db.log(
                "INFO",
                f"[Strategy Router] {desk}: Dispatched '{best_strat.name}' (Suitability Score: {best_score:.2f}, Regime: {context.get('regime', 'Neutral')})"
            )

        return best_strat

    def route_fno(self, target: str = "NIFTY", context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Selects and executes optimal F&O strategy (Credit vs Debit)."""
        context = context or {}
        best_strat = self.select_best_strategy("FNO", context)
        if best_strat:
            return best_strat.propose(target, context=context)
        return None

    def route_intraday(self, symbol: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Selects and executes optimal Intraday strategy (ORB vs VWAP Pullback)."""
        context = context or {}
        best_strat = self.select_best_strategy("INTRADAY", context)
        if best_strat:
            return best_strat.propose(symbol, context=context)
        return None

    def route_swing(self, symbol: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Selects and executes optimal Swing strategy (Pullback vs Momentum Breakout)."""
        context = context or {}
        best_strat = self.select_best_strategy("SWING", context)
        if best_strat:
            return best_strat.propose(symbol, context=context)
        return None
