"""
Sleeves package for systematic multi-sleeve architecture.
- Sleeve A: Cross-Sectional Momentum (app/sleeves/momentum.py)
- Sleeve B: Index Trend Following (app/sleeves/trend.py)
- Sleeve C: Short-Term Mean Reversion (app/sleeves/meanrev.py)
- Sleeve D: Defined-Risk Premium Selling (app/sleeves/premium.py)
"""

from .momentum import decide as decide_momentum
from .trend import decide as decide_trend
from .meanrev import decide as decide_meanrev
from .premium import (
    decide as decide_premium,
    calculate_option_sell_stt,
    evaluate_condor_risk_rule,
    check_condor_exits,
    IronCondor,
    OptionLeg,
    generate_sleeve_d_report,
)
from .combined_portfolio import run_combined_backtest, generate_combined_portfolio_report

__all__ = [
    "decide_momentum",
    "decide_trend",
    "decide_meanrev",
    "decide_premium",
    "calculate_option_sell_stt",
    "evaluate_condor_risk_rule",
    "check_condor_exits",
    "IronCondor",
    "OptionLeg",
    "generate_sleeve_d_report",
    "run_combined_backtest",
    "generate_combined_portfolio_report",
]
