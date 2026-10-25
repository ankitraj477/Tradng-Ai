"""
Portfolio & Risk Management Layer for multi-sleeve architecture.
Enforces Section 9 & Section 10 (Test 9, Test 10):
- Cross-sleeve symbol ownership: symbol held by sleeve A cannot be opened by sleeve C.
- Gross exposure cap <= 100% of equity (no leverage).
- Portfolio heat cap <= 6% of equity.
- Sector exposure cap <= 25% of equity.
- Daily loss limit: -2% halts entries for remainder of the day.
- Drawdown ladder: -5% halves size (x0.5); -10% halts entries until audited reset.
- Sleeve drift monitoring: disables underperforming sleeves based on 30-trade rolling mean.
"""

from typing import Dict, List, Optional, Tuple, Set
from datetime import date
from .simulate import Proposal
from .ledger import Ledger


class PortfolioRiskManager:
    """Comprehensive multi-sleeve portfolio and risk governor."""

    def __init__(self, cfg=None):
        self.cfg = cfg
        raw_risk = getattr(cfg, "raw", {}).get("portfolio_risk", {}) if cfg else {}

        self.gross_exposure_cap: float = float(raw_risk.get("gross_exposure_cap", 1.00))
        self.max_heat_pct: float = float(raw_risk.get("max_portfolio_heat_pct", 0.06))
        self.max_sector_pct: float = float(raw_risk.get("max_sector_exposure_pct", 0.25))
        self.daily_loss_limit_pct: float = float(raw_risk.get("daily_loss_limit_pct", 0.02))

        ladder = raw_risk.get("drawdown_ladder", {})
        self.dd_tier1_pct: float = float(ladder.get("tier1_pct", 0.05))
        self.dd_tier1_mult: float = float(ladder.get("tier1_size_multiplier", 0.5))
        self.dd_tier2_pct: float = float(ladder.get("tier2_pct", 0.10))

        # Peak equity & state tracking
        self.peak_equity: float = 0.0
        self.day_start_equity: float = 0.0
        self.daily_halt_triggered: bool = False
        self.tier2_halt_triggered: bool = False
        self.manual_resets_log: List[Dict[str, str]] = []

        # Sleeve performance tracking for drift detection
        self.sleeve_recent_trades: Dict[str, List[float]] = {"A": [], "B": [], "C": [], "D": []}
        self.disabled_sleeves: Set[str] = set()

    def update_equity_peaks(self, current_equity: float):
        """Update peak equity and day start equity."""
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
        if self.day_start_equity <= 0:
            self.day_start_equity = current_equity

    def reset_daily_metrics(self, starting_equity: float):
        """Called at start of each new trading session."""
        self.day_start_equity = starting_equity
        self.daily_halt_triggered = False

    def get_drawdown_pct(self, current_equity: float) -> float:
        """Calculate current drawdown percentage from peak."""
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - current_equity) / self.peak_equity)

    def get_daily_return_pct(self, current_equity: float) -> float:
        """Calculate day's return relative to session start."""
        if self.day_start_equity <= 0:
            return 0.0
        return (current_equity - self.day_start_equity) / self.day_start_equity

    def manual_reset_drawdown(self, reason: str, authorized_by: str = "AUDITOR") -> bool:
        """Audited command to reset drawdown ladder halt."""
        if not reason or len(reason.strip()) < 5:
            raise ValueError("Audited manual reset requires an explicit substantive reason.")
        self.manual_resets_log.append({
            "timestamp": str(date.today()),
            "reason": reason.strip(),
            "authorized_by": authorized_by
        })
        self.tier2_halt_triggered = False
        return True

    def record_closed_trade(self, sleeve: str, return_pct: float):
        """Track sleeve performance and trigger drift switch if underperforming."""
        s = sleeve.upper()
        if s not in self.sleeve_recent_trades:
            self.sleeve_recent_trades[s] = []
        self.sleeve_recent_trades[s].append(return_pct)
        if len(self.sleeve_recent_trades[s]) > 30:
            self.sleeve_recent_trades[s].pop(0)

        # Drift check on rolling 30 trades: if mean return < -2.0% (5th percentile bootstrap threshold)
        if len(self.sleeve_recent_trades[s]) >= 30:
            mean_ret = sum(self.sleeve_recent_trades[s]) / 30.0
            if mean_ret < -0.02:  # -2% mean return threshold
                self.disabled_sleeves.add(s)

    def evaluate_proposal(
        self,
        proposal: Proposal,
        ledger: Ledger,
        current_equity: float,
        proposed_price: float,
        sector_lookup: Optional[Dict[str, str]] = None
    ) -> Tuple[bool, str, int]:
        """
        Evaluate order proposal against all unified portfolio and risk gates.
        Returns: (approved: bool, reason: str, adjusted_qty: int)
        """
        self.update_equity_peaks(current_equity)
        sleeve = proposal.sleeve.upper()

        # 1. Sleeve drift check
        if sleeve in self.disabled_sleeves:
            return False, f"Sleeve {sleeve} is disabled by drift switch", 0

        # 2. Daily loss limit (-2% halt)
        daily_ret = self.get_daily_return_pct(current_equity)
        if daily_ret <= -self.daily_loss_limit_pct:
            self.daily_halt_triggered = True
            return False, f"Daily loss limit breached ({daily_ret*100:.2f}% <= -{self.daily_loss_limit_pct*100:.1f}%)", 0

        if self.daily_halt_triggered:
            return False, "Daily trading halt active", 0

        # 3. Drawdown ladder
        dd = self.get_drawdown_pct(current_equity)
        if dd >= self.dd_tier2_pct:
            self.tier2_halt_triggered = True

        if self.tier2_halt_triggered:
            return False, f"Drawdown ladder Tier 2 halt active ({dd*100:.2f}% >= {self.dd_tier2_pct*100:.1f}%)", 0

        size_mult = 1.0
        if dd >= self.dd_tier1_pct:
            size_mult = self.dd_tier1_mult  # Halve size (x0.5)

        # 4. Cross-sleeve ownership check (Section 4 & Test 9)
        # A symbol held by any sleeve cannot be opened by another sleeve
        for (pos_sleeve, pos_sym) in ledger.positions.keys():
            if pos_sym == proposal.symbol and pos_sleeve != proposal.sleeve:
                return False, f"Symbol {proposal.symbol} already held by sleeve {pos_sleeve} (ownership violation)", 0

        # If selling, no new risk added
        if proposal.side.upper() in ("SELL", "SHORT"):
            existing = ledger.get_position(proposal.sleeve, proposal.symbol)
            if not existing or existing.qty < (proposal.qty or 0):
                return False, "Cannot sell more than held quantity", 0
            return True, "Approved sell", proposal.qty

        # Sizing with multiplier
        qty = max(1, int((proposal.qty or 1) * size_mult))
        order_value = qty * proposed_price

        # 5. Gross exposure cap (<= 100% equity; no leverage)
        current_invested = ledger.marked_entry_value
        if (current_invested + order_value) > current_equity * self.gross_exposure_cap + 1e-4:
            return False, f"Gross exposure cap ({self.gross_exposure_cap*100:.0f}%) exceeded", 0

        # 6. Sector cap (<= 25% of equity per sector)
        if sector_lookup:
            sector = sector_lookup.get(proposal.symbol, "General")
            sector_invested = sum(pos.qty * pos.entry_price for pos in ledger.positions.values()
                                  if sector_lookup.get(pos.symbol) == sector)
            if (sector_invested + order_value) > current_equity * self.max_sector_pct + 1e-4:
                return False, f"Sector cap for {sector} ({self.max_sector_pct*100:.0f}%) exceeded", 0

        # 7. Portfolio heat cap (<= 6% equity)
        if proposal.stop is not None and proposal.stop > 0:
            new_risk = abs(proposed_price - proposal.stop) * qty
            # Existing portfolio risk
            existing_risk = 0.0
            for pos in ledger.positions.values():
                # Estimate stop distance as 2.0 * ATR or 5% if not recorded
                existing_risk += pos.qty * pos.entry_price * 0.05
            if (existing_risk + new_risk) > current_equity * self.max_heat_pct + 1e-4:
                return False, f"Portfolio heat cap ({self.max_heat_pct*100:.1f}%) exceeded", 0

        return True, "Approved", qty
