"""
Milestone 7 Test Suite: Sleeve D (Defined-Risk Premium Selling on NIFTY).
Enforces Section 8, Section 10 (Test 2, Test 12), Section 11 (M7), and Section 12 criteria:
- Test 2: Delivery & Option STT calculation (65 units @ 40 INR premium = 3.90 INR STT).
- Test 12: A condor violating the 1% rule is skipped.
- Test 12: Delta-breach exit (|delta| >= 0.30) fires.
- Test 12: DTE <= 3 exit fires.
- Test 12: No expiry-day holding (DTE == 0 fires).
- Fail-closed requirement: missing chain snapshot returns empty proposals.
- Take-profit (debit <= 50% credit) and stop-loss (debit >= 2x credit) exits.
- Report generation: reports/sleeve_d_report.md.
"""

from pathlib import Path
from typing import Dict, List, Any
import pytest

from app.sleeves.premium import (
    calculate_option_sell_stt,
    evaluate_condor_risk_rule,
    check_condor_exits,
    decide,
    IronCondor,
    OptionLeg,
    generate_sleeve_d_report,
)
from app.strategy_config import load_strategy_config


# ----------------------------------------------------------------------
# 1. Test 2: Statutory Option STT Reconciliation
# ----------------------------------------------------------------------

def test_m7_option_stt_reconciliation_test2():
    """
    Test 2 & Section 8 & Section 10:
    Selling 65 units at a premium of 40 INR costs:
    0.0015 * 40 * 65 = 3.9 INR STT.
    """
    stt = calculate_option_sell_stt(premium=40.0, qty=65)
    assert abs(stt - 3.90) < 1e-4, f"Expected 3.90 INR STT, got {stt}"

    # Zero premium or zero quantity gives zero STT
    assert calculate_option_sell_stt(premium=0.0, qty=65) == 0.0
    assert calculate_option_sell_stt(premium=40.0, qty=0) == 0.0


# ----------------------------------------------------------------------
# 2. Test 12: 1% Max Loss Rule (Violating Condor Skipped)
# ----------------------------------------------------------------------

def test_m7_condor_violating_1pct_rule_is_skipped_test12():
    """
    Test 12 & Section 8:
    max_loss = (W - net_credit) * lot must be <= 1% of option notional equity.
    Otherwise SKIP!
    """
    option_equity = 1000000.0  # 10 Lakhs -> 1% cap = 10,000 INR
    lot_size = 65

    # Case 1: Wide wings (W=200, credit=20) -> max_loss = (200 - 20) * 65 = 11,700 INR > 10,000 INR
    # MUST BE SKIPPED!
    approved_wide, max_loss_wide, reason_wide = evaluate_condor_risk_rule(
        wing_width=200.0,
        net_credit=20.0,
        lot_size=lot_size,
        option_notional_equity=option_equity,
        max_loss_pct=0.01
    )
    assert approved_wide is False
    assert max_loss_wide == 11700.0
    assert "exceeds 1% equity limit" in reason_wide.lower()

    # Case 2: Narrow wings (W=100, credit=25) -> max_loss = (100 - 25) * 65 = 4,875 INR <= 10,000 INR
    # AND credit/W = 25/100 = 0.25 >= 0.15
    # MUST BE APPROVED!
    approved_narrow, max_loss_narrow, reason_narrow = evaluate_condor_risk_rule(
        wing_width=100.0,
        net_credit=25.0,
        lot_size=lot_size,
        option_notional_equity=option_equity,
        max_loss_pct=0.01
    )
    assert approved_narrow is True
    assert max_loss_narrow == 4875.0
    assert "approved" in reason_narrow.lower()

    # Case 3: Insufficient credit ratio (credit=10, W=100 -> credit/W = 0.10 < 0.15)
    # MUST BE SKIPPED!
    approved_ratio, _, reason_ratio = evaluate_condor_risk_rule(
        wing_width=100.0,
        net_credit=10.0,
        lot_size=lot_size,
        option_notional_equity=option_equity,
        max_loss_pct=0.01
    )
    assert approved_ratio is False
    assert "below minimum 0.15" in reason_ratio.lower()


# ----------------------------------------------------------------------
# 3. Test 12: Delta-Breach, DTE, and Expiry Exits
# ----------------------------------------------------------------------

def test_m7_condor_exits_delta_breach_and_dte_test12():
    """
    Test 12 & Section 8 Exits:
    - Delta breach: any short strike |delta| >= 0.30 -> exit.
    - DTE exit: DTE <= 3 -> exit.
    - No expiry day holding: DTE == 0 -> exit.
    - Take profit: debit <= 50% credit.
    - Stop loss: debit >= 2x credit.
    """
    condor = IronCondor(
        expiry="2026-05-28",
        short_call=OptionLeg(symbol="NIFTY26MAY24500CE", strike=24500.0, option_type="CE", side="SELL", qty=65, premium=50.0, delta=0.12),
        long_call=OptionLeg(symbol="NIFTY26MAY24600CE", strike=24600.0, option_type="CE", side="BUY", qty=65, premium=20.0, delta=0.05),
        short_put=OptionLeg(symbol="NIFTY26MAY23500PE", strike=23500.0, option_type="PE", side="SELL", qty=65, premium=45.0, delta=-0.12),
        long_put=OptionLeg(symbol="NIFTY26MAY23400PE", strike=23400.0, option_type="PE", side="BUY", qty=65, premium=18.0, delta=-0.05),
        wing_width=100.0,
        lot_size=65,
        net_credit=57.0,  # (50 + 45) - (20 + 18) = 95 - 38 = 57.0
        max_loss=2795.0,
        entry_dte=35,
        opened_at="2026-04-23"
    )

    # 1. Normal Holding: delta = 0.14, DTE = 20, debit = 40 -> HOLD
    exit_normal, why_normal = check_condor_exits(
        condor=condor,
        current_quotes={"NIFTY26MAY24500CE": 35.0, "NIFTY26MAY24600CE": 12.0, "NIFTY26MAY23500PE": 30.0, "NIFTY26MAY23400PE": 10.0},
        current_deltas={"NIFTY26MAY24500CE": 0.14, "NIFTY26MAY23500PE": -0.13},
        current_dte=20
    )
    assert exit_normal is False
    assert why_normal == "Holding"

    # 2. Delta Breach on Short Call: delta jumps to 0.32 >= 0.30 -> EXIT
    exit_delta, why_delta = check_condor_exits(
        condor=condor,
        current_quotes={"NIFTY26MAY24500CE": 75.0, "NIFTY26MAY24600CE": 40.0, "NIFTY26MAY23500PE": 15.0, "NIFTY26MAY23400PE": 5.0},
        current_deltas={"NIFTY26MAY24500CE": 0.32, "NIFTY26MAY23500PE": -0.08},
        current_dte=20
    )
    assert exit_delta is True
    assert "delta breach" in why_delta.lower()

    # 3. DTE Exit: DTE <= 3 (DTE=3) -> EXIT
    exit_dte, why_dte = check_condor_exits(
        condor=condor,
        current_quotes={"NIFTY26MAY24500CE": 20.0, "NIFTY26MAY24600CE": 5.0, "NIFTY26MAY23500PE": 15.0, "NIFTY26MAY23400PE": 4.0},
        current_deltas={"NIFTY26MAY24500CE": 0.08, "NIFTY26MAY23500PE": -0.06},
        current_dte=3
    )
    assert exit_dte is True
    assert "dte threshold exit" in why_dte.lower()

    # 4. Never Hold Into Expiry Day: DTE == 0 -> EXIT
    exit_exp, why_exp = check_condor_exits(
        condor=condor,
        current_quotes={"NIFTY26MAY24500CE": 10.0, "NIFTY26MAY24600CE": 0.0, "NIFTY26MAY23500PE": 5.0, "NIFTY26MAY23400PE": 0.0},
        current_deltas={"NIFTY26MAY24500CE": 0.05, "NIFTY26MAY23500PE": -0.02},
        current_dte=0
    )
    assert exit_exp is True
    assert "expiry day exit guard" in why_exp.lower()

    # 5. Take Profit: debit to close <= 50% credit (57 * 0.50 = 28.50)
    # debit = (18 + 15) - (4 + 3) = 26.0 <= 28.50 -> EXIT
    exit_tp, why_tp = check_condor_exits(
        condor=condor,
        current_quotes={"NIFTY26MAY24500CE": 18.0, "NIFTY26MAY24600CE": 4.0, "NIFTY26MAY23500PE": 15.0, "NIFTY26MAY23400PE": 3.0},
        current_deltas={"NIFTY26MAY24500CE": 0.06, "NIFTY26MAY23500PE": -0.05},
        current_dte=15
    )
    assert exit_tp is True
    assert "take profit" in why_tp.lower()

    # 6. Stop Loss: debit >= 2x credit (57 * 2.0 = 114.0)
    # debit = (85 + 70) - (20 + 15) = 155 - 35 = 120.0 >= 114.0 -> EXIT
    exit_sl, why_sl = check_condor_exits(
        condor=condor,
        current_quotes={"NIFTY26MAY24500CE": 85.0, "NIFTY26MAY24600CE": 20.0, "NIFTY26MAY23500PE": 70.0, "NIFTY26MAY23400PE": 15.0},
        current_deltas={"NIFTY26MAY24500CE": 0.22, "NIFTY26MAY23500PE": -0.21},
        current_dte=15
    )
    assert exit_sl is True
    assert "stop loss" in why_sl.lower()


# ----------------------------------------------------------------------
# 4. Fail-Closed Requirement (Section 8)
# ----------------------------------------------------------------------

def test_m7_fail_closed_without_option_chain_snapshot():
    """
    Section 8:
    'Do not build until option-chain snapshots exist. Without them, mark the sleeve DISABLED and fail closed.'
    """
    sleeve_cfg_disabled = {
        "enabled": False,
        "option_notional_equity": 1000000.0
    }
    portfolio_state = {"asof": "2026-05-04", "open_condors": []}

    # Case 1: Sleeve disabled in config -> returns empty proposals (fail closed)
    proposals_disabled = decide(
        sleeve_cfg=sleeve_cfg_disabled,
        chain_snapshot={"quotes": {}, "deltas": {}},
        portfolio_state=portfolio_state
    )
    assert len(proposals_disabled) == 0

    # Case 2: Chain snapshot is None -> returns empty proposals (fail closed)
    sleeve_cfg_enabled = {
        "enabled": True,
        "option_notional_equity": 1000000.0
    }
    proposals_no_snapshot = decide(
        sleeve_cfg=sleeve_cfg_enabled,
        chain_snapshot=None,
        portfolio_state=portfolio_state
    )
    assert len(proposals_no_snapshot) == 0

    # Case 3: Empty chain snapshot -> returns empty proposals (fail closed)
    proposals_empty = decide(
        sleeve_cfg=sleeve_cfg_enabled,
        chain_snapshot={},
        portfolio_state=portfolio_state
    )
    assert len(proposals_empty) == 0


# ----------------------------------------------------------------------
# 5. Condor Decision & Proposal Generation with Snapshot
# ----------------------------------------------------------------------

def test_m7_condor_decision_and_order_generation_with_snapshot():
    """
    When validated option chain snapshot is present and all filters pass:
    Generates exact 4-leg Iron Condor proposals (SELL SC, BUY LC, SELL SP, BUY LP).
    """
    cfg = {
        "enabled": True,
        "option_notional_equity": 1000000.0,
        "max_open_condors": 2,
        "wing_width": 100,
        "min_iv_rank": 50.0,
        "target_delta": 0.12,
        "delta_min": 0.10,
        "delta_max": 0.16,
        "lot_size": 65
    }

    # Synthetic valid snapshot
    snapshot = {
        "dte": 35,
        "iv_rank": 62.0,
        "atm_iv30": 15.5,
        "realized_vol20": 12.0,  # IV30 - RV20 > 0
        "vix_5d_change_pct": 0.05,  # <= 20%
        "calls": [
            {"symbol": "NIFTY_24500_CE", "strike": 24500.0, "delta": 0.12, "premium": 55.0},
            {"symbol": "NIFTY_24600_CE", "strike": 24600.0, "delta": 0.06, "premium": 22.0},
        ],
        "puts": [
            {"symbol": "NIFTY_23500_PE", "strike": 23500.0, "delta": -0.12, "premium": 48.0},
            {"symbol": "NIFTY_23400_PE", "strike": 23400.0, "delta": -0.05, "premium": 19.0},
        ],
        "quotes": {},
        "deltas": {}
    }

    proposals = decide(
        sleeve_cfg=cfg,
        chain_snapshot=snapshot,
        portfolio_state={"asof": "2026-05-04", "open_condors": []}
    )

    assert len(proposals) == 4
    symbols = {p.symbol for p in proposals}
    assert "NIFTY_24500_CE" in symbols
    assert "NIFTY_24600_CE" in symbols
    assert "NIFTY_23500_PE" in symbols
    assert "NIFTY_23400_PE" in symbols

    sides = {p.symbol: p.side for p in proposals}
    assert sides["NIFTY_24500_CE"] == "SELL"
    assert sides["NIFTY_24600_CE"] == "BUY"
    assert sides["NIFTY_23500_PE"] == "SELL"
    assert sides["NIFTY_23400_PE"] == "BUY"

    for p in proposals:
        assert p.sleeve == "D"
        assert p.qty == 65


# ----------------------------------------------------------------------
# 6. Report Generation
# ----------------------------------------------------------------------

def test_m7_sleeve_d_report_generation():
    """
    Test Milestone 7 Acceptance Report generation:
    - Generates reports/sleeve_d_report.md.
    - Asserts gate acceptance decision.
    """
    report_file = generate_sleeve_d_report(output_path="reports/sleeve_d_report.md")
    report_path = Path(report_file)
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")

    assert "Sleeve D (Defined-Risk Premium Selling) Acceptance Report" in content
    assert "**Overall Gate D Decision:** **ACCEPTED" in content
    assert "| **Fail-Closed Rule** |" in content
    assert "| **Test 12: 1% Max Loss Rule** |" in content
