import numpy as np
import pandas as pd
from .costs import CostModel


class VolatilityTargetedSizer:
    """
    Volatility-targeted position sizer based on ATR and portfolio equity.
    Maintains constant risk exposure across varying volatility regimes and account sizes.
    """
    def __init__(self, target_risk_pct=0.015, atr_multiplier=1.5, max_position_pct=0.20):
        self.target_risk = float(target_risk_pct)
        self.atr_mult = float(atr_multiplier)
        self.max_pos_pct = float(max_position_pct)

    def size(self, equity, price, atr):
        if equity <= 0 or price <= 0:
            return 0
        risk_budget = equity * self.target_risk
        per_share_risk = max(float(atr) * self.atr_mult, float(price) * 0.005)
        qty_by_risk = int(risk_budget / per_share_risk)

        # Hard position notional cap
        max_notional = equity * self.max_pos_pct
        qty_by_cap = int(max_notional / price)

        return max(0, min(qty_by_risk, qty_by_cap))


class MinimumMoveGate:
    """
    Cost-aware execution filter.
    Requires expected target move to be >= k * total round-trip transaction costs.
    Prevents churning the account on microscopic edges eaten alive by fees.
    """
    def __init__(self, cost_multiplier=3.0, cost_model=None):
        self.k = float(cost_multiplier)
        self.cost_model = cost_model or CostModel()

    def check(self, price, target, stop_loss, action="BUY", segment="INTRADAY"):
        expected_move = abs(float(target) - float(price))
        # Approximate round-trip fee for 1 share
        entry_fee = self.cost_model.calculate(price, action, segment)
        exit_fee = self.cost_model.calculate(target, "SELL" if action == "BUY" else "BUY", segment)
        round_trip_cost = entry_fee + exit_fee

        required_move = self.k * round_trip_cost
        if expected_move < required_move:
            return False, f"Expected move ₹{expected_move:.2f} < {self.k}x round-trip cost ₹{required_move:.2f}"
        return True, "Pass"


class PortfolioHeatLimiter:
    """
    Enforces total open portfolio heat (total capital at risk across all open stop losses).
    Max Heat Limit = sum(qty * abs(current_price - stop_loss)) <= max_heat_pct * Equity.
    """
    def __init__(self, max_heat_pct=0.06, max_sector_pct=0.40):
        self.max_heat = float(max_heat_pct)
        self.max_sector = float(max_sector_pct)

    def check(self, equity, open_positions, new_proposal, new_qty):
        if equity <= 0: return False, "Zero equity"

        # 1. Existing Heat
        current_heat = sum(
            float(p["qty"]) * max(abs(float(p.get("current_price", p["entry_price"])) - float(p.get("stop_loss", p["entry_price"]))), 0.01)
            for p in open_positions
        )
        new_risk = float(new_qty) * max(abs(float(new_proposal["price"]) - float(new_proposal["stop_loss"])), 0.01)
        total_heat = current_heat + new_risk
        allowed_heat = equity * self.max_heat

        if total_heat > allowed_heat:
            return False, f"Portfolio heat {total_heat:.2f} exceeds limit {allowed_heat:.2f} ({self.max_heat*100:.1f}%)"

        # 2. Sector Cap
        sec = new_proposal.get("sector")
        if sec and sec != "Unknown":
            sec_exposure = sum(
                float(p["qty"]) * float(p.get("current_price", p["entry_price"]))
                for p in open_positions if p.get("sector") == sec
            ) + (float(new_qty) * float(new_proposal["price"]))
            sec_limit = equity * self.max_sector
            if sec_exposure > sec_limit:
                return False, f"Sector {sec} exposure {sec_exposure:.2f} exceeds limit {sec_limit:.2f}"

        return True, "Pass"


class StrategyDriftKillSwitch:
    """
    Per-strategy performance drift kill switch.
    Automatically pauses a strategy if its rolling live expectancy falls below
    the backtest statistical lower bound.
    """
    def __init__(self, rolling_window=20, min_trades=10):
        self.window = int(rolling_window)
        self.min_trades = int(min_trades)
        self.history = {}  # strategy -> list of net realized trade PnLs
        self.lower_bounds = {}  # strategy -> lower bound threshold

    def register_baseline(self, strategy_name, lower_bound=0.0):
        self.lower_bounds[strategy_name] = float(lower_bound)

    def record_trade(self, strategy_name, pnl):
        if strategy_name not in self.history:
            self.history[strategy_name] = []
        self.history[strategy_name].append(float(pnl))

    def is_paused(self, strategy_name):
        trades = self.history.get(strategy_name, [])
        if len(trades) < self.min_trades:
            return False, "Insufficient live sample"

        recent = trades[-self.window:]
        rolling_exp = float(np.mean(recent))
        bound = self.lower_bounds.get(strategy_name, 0.0)

        if rolling_exp < bound:
            return True, f"Strategy {strategy_name} paused on performance drift: rolling expectancy {rolling_exp:.2f} < bound {bound:.2f}"
        return False, "Active"
