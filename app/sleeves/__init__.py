"""
Sleeves package for systematic multi-sleeve architecture.
- Sleeve A: Cross-Sectional Momentum (app/sleeves/momentum.py)
- Sleeve B: Index Trend Following (app/sleeves/trend.py)
- Sleeve C: Short-Term Mean Reversion (app/sleeves/meanrev.py)
- Sleeve D: Defined-Risk Premium Selling (app/sleeves/premium.py)
"""

from .momentum import decide as decide_momentum

__all__ = ["decide_momentum"]
