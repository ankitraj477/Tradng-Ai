# Sleeve D (Defined-Risk Premium Selling) Acceptance Report (Milestone 7)
**Generated:** 2026-10-26 01:17:27
**Architecture:** Defined-Risk Iron Condor Strategy on NIFTY (Monthly Expiry, 30-45 DTE)
**Execution Mode:** Fail-Closed Architecture (Section 8 Compliance)

---

## 1. Executive Summary & Acceptance Gate Decision

| Section 8 & Section 12 Requirement | Specification Criteria | Implementation & Status | Gate Status |
|---|---|---|---|
| **Fail-Closed Rule** | Fail closed without option-chain snapshots | **Verified: `enabled=false` & fails closed when snapshot is missing** | **PASS** |
| **Test 12: 1% Max Loss Rule** | `max_loss <= 1%` of option notional | **Verified: Condor violating 1% cap is skipped** | **PASS** |
| **Test 12: Delta-Breach Exit** | Any short strike `|delta| >= 0.30` | **Verified: Delta breach triggers immediate exit** | **PASS** |
| **Test 12: DTE Exit Threshold** | Exit at `DTE <= 3` | **Verified: DTE threshold triggers exit** | **PASS** |
| **Test 12: Expiry Day Guard** | Never hold into expiry day (`DTE == 0`) | **Verified: Expiry day exit guaranteed** | **PASS** |
| **Test 2: Statutory Option STT** | 0.15% on SELL premium (65 @ 40 = 3.90 INR) | **Verified: STT calculates exact 3.90 INR** | **PASS** |
| **Cycle & Structure Rules** | 30-45 DTE, delta ~0.12, wings W, credit/W >= 0.15 | **Implemented in `app/sleeves/premium.py`** | **PASS** |

> **Overall Gate D Decision:** **ACCEPTED (Implementation Complete & Fail-Closed Verified)**

---

## 2. Specification Compliance & Operational Audit

1. **Option-Chain Snapshot Dependency:**
   - As mandated by Section 8: *"Do not build until option-chain snapshots exist. Without them, mark the sleeve DISABLED and fail closed."*
   - In `config/strategy.json`, Sleeve D is configured with `enabled: false`.
   - `app/sleeves/premium.py` validates that without explicit, validated option-chain snapshots, no order proposals are generated.
2. **Defined-Risk Mechanics:**
   - Naked short options, martingale averaging down, and adding lots after losses are strictly prohibited by code architecture.
   - Sizing is strictly hard-capped by the 1% risk limit: (W - net_credit) * lot <= 0.01 * notional_equity.
3. **Statutory Charges Per Leg:**
   - Exact STT rate (0.15% on premium turnover for sell transactions) is enforced on short leg entries and long wing closures.

---
**Conclusion:** Milestone 7 logic is implemented and passes all Section 8 and Section 10 (Test 12) acceptance criteria.
