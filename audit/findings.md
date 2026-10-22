# Codebase Audit Findings Register

This document registers all verified security vulnerabilities, functional defects, exchange microstructure compliance issues, and data invariants identified during the repository-wide audit.

---

## Summary of Findings by Severity

| Severity | Count | Fixed | Disposition |
|---|---|---|---|
| **Critical** | 0 | 0 | None identified in in-scope modules |
| **High** | 1 | 1 | Verified & Fixed (AUDIT-001) |
| **Medium** | 4 | 4 | Verified & Fixed (AUDIT-002, AUDIT-003, AUDIT-004, AUDIT-005) |
| **Low** | 2 | 2 | Verified & Fixed (AUDIT-006, AUDIT-007) |
| **Informational** | 0 | 0 | Documented |
| **Total** | **7** | **7** | **100% Remediated** |

---

## Detailed Findings Register

### AUDIT-001: Unhandled `None` Account Fetch in Risk, Accounting & Execution Engines
- **Severity:** High
- **Confidence:** High
- **Category:** Functional Correctness / Crash Vulnerability
- **Affected Files:**
  - `app/accounting.py` (lines 2-4)
  - `app/risk.py` (lines 94-110, 179-195)
  - `app/fno/execution.py` (lines 40-47)
  - `app/intraday/execution.py` (lines 146-150, 177-184)
- **Affected Workflow:** Portfolio valuation, pre-trade risk checks, F&O spread execution, and intraday MIS order placement.
- **Evidence:** Code called `acc = dict(c.execute("SELECT * FROM account WHERE id=1").fetchone())`. If called before initial account seeding or during transient migrations, `fetchone()` returns `None`, resulting in `TypeError: 'NoneType' object is not iterable` and an unhandled 500 error or engine abort.
- **Trigger Conditions:** Initial system boot without manual DB seeding, cold test runner execution, or transient database re-creation.
- **Expected vs Actual:**
  - *Expected:* Safe fallback to default empty account with defensive table seeding or zero cash defaults.
  - *Actual:* Fatal `TypeError` crash halting trading loops and API endpoints.
- **Impact:** System denial-of-service on first startup; potential trade execution failure during engine cold boot.
- **Remediation:** Added defensive fallback row insertion (`INSERT OR IGNORE INTO account ...`) and default dictionary fallbacks (`account = account or {}`, `acc = dict(row) if row else {"cash": 0.0, ...}`).
- **Regression Tests:** `tests/test_audit_security_and_invariants.py::test_accounting_with_none_account`, `test_risk_manager_with_empty_account`, `test_intraday_execution_tick_rounding_and_defensive_account`, `test_fno_execution_tick_rounding_and_defensive_account`.
- **Status:** **VERIFIED & FIXED**

---

### AUDIT-002: Timing Side-Channel Vulnerability in Dashboard Token Authentication (CWE-208)
- **Severity:** Medium
- **Confidence:** High
- **Category:** Application Security / Authentication
- **Affected Files:** `app/dashboard.py` (line 2021)
- **Affected Workflow:** Dashboard authentication (`Authorization: Bearer <token>`, `X-API-Token`, and `?token=` query param).
- **Evidence:** `_is_authorized()` executed `return token == dashboard_token`. Python's native string equality (`==`) terminates comparison at the first mismatched byte, leaking token length and prefix characters via timing side-channels.
- **Trigger Conditions:** Attacker measuring sub-millisecond response latency variations across candidate token guesses.
- **Expected vs Actual:**
  - *Expected:* Constant-time token comparison preventing timing attacks.
  - *Actual:* Early-exit byte-by-byte comparison vulnerable to timing analysis.
- **Impact:** Exposure of dashboard control token, allowing unauthorized configuration edits, kill-switch toggling, or capital re-allocation.
- **Remediation:** Replaced variable-time string comparison with `hmac.compare_digest(token, dashboard_token)`.
- **Regression Tests:** `tests/test_audit_security_and_invariants.py::test_dashboard_security_headers_and_token`.
- **Status:** **VERIFIED & FIXED**

---

### AUDIT-003: Missing HTTP Security Headers on Dashboard API Endpoints
- **Severity:** Medium
- **Confidence:** High
- **Category:** Application Security / Defense-in-Depth
- **Affected Files:** `app/dashboard.py` (lines 2013-2025)
- **Affected Workflow:** Web dashboard rendering and REST API response delivery.
- **Evidence:** Flask response headers lacked `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`, and `Content-Security-Policy`.
- **Trigger Conditions:** Dashboard accessed via browser in enterprise or shared network environments.
- **Expected vs Actual:**
  - *Expected:* Standard OWASP-recommended security headers preventing clickjacking, MIME sniffing, and cross-site framing.
  - *Actual:* Bare responses with default Werkzeug headers.
- **Impact:** Susceptibility to clickjacking (embedding trading dashboard in malicious iframes) and MIME sniffing attacks.
- **Remediation:** Implemented `@flask_app.after_request` handler applying `nosniff`, `SAMEORIGIN`, `strict-origin-when-cross-origin`, and strict CSP headers.
- **Regression Tests:** `tests/test_audit_security_and_invariants.py::test_dashboard_security_headers_and_token`.
- **Status:** **VERIFIED & FIXED**

---

### AUDIT-004: Missing 5-Paise Tick Size Rounding & Microstructure Validations
- **Severity:** Medium
- **Confidence:** High
- **Category:** Exchange Compliance / Execution Microstructure
- **Affected Files:**
  - `app/intraday/execution.py` (lines 139-202)
  - `app/fno/execution.py` (lines 35-95)
- **Affected Workflow:** Intraday MIS orders, stop-losses, profit targets, F&O spread entry credits, and position exits.
- **Evidence:** `open_long`, `open_short`, and `open_spread` accepted arbitrary floating-point prices (e.g. ₹1000.134, ₹42.13) without normalizing to Indian exchange standard 5-paise (₹0.05) tick boundaries.
- **Trigger Conditions:** Algorithm generating price targets or ATR trailing stops with arbitrary floating-point fractions.
- **Expected vs Actual:**
  - *Expected:* All order prices, stops, and targets strictly quantized to nearest 0.05 tick (e.g. 1000.13 -> 1000.15) and checked against circuit filters.
  - *Actual:* Sub-tick prices passed to simulated positions and broker adapters.
- **Impact:** Order rejections from NSE/BSE exchange matching engines when switching from paper to live trading.
- **Remediation:** Integrated `round_to_tick()` and `validate_order_microstructure()` across entry prices, stops, targets, and exit fills.
- **Regression Tests:** `tests/test_audit_security_and_invariants.py::test_intraday_execution_tick_rounding_and_defensive_account`, `test_fno_execution_tick_rounding_and_defensive_account`.
- **Status:** **VERIFIED & FIXED**

---

### AUDIT-005: Unclamped / Negative Capital Allocation Invariant Violation
- **Severity:** Medium
- **Confidence:** High
- **Category:** Data Integrity / Business Invariant
- **Affected Files:**
  - `app/db.py` (lines 331-343)
  - `app/dashboard.py` (lines 2132-2143)
- **Affected Workflow:** Multi-desk capital rebalancing across Intraday, Swing, and F&O desks.
- **Evidence:** `set_capital_allocation(intraday, swing, fno)` accepted arbitrary numeric values without validating `value >= 0.0`. If a negative value (e.g. -50%) was sent via `/api/capital-allocation`, it produced distorted or negative percentages, breaking desk allocation constraints.
- **Trigger Conditions:** Malformed API payload or invalid UI input submitted to `/api/capital-allocation`.
- **Expected vs Actual:**
  - *Expected:* All allocations clamped to non-negative floats (`max(0.0, float(x))`) and normalized to sum to 100.0%.
  - *Actual:* Negative inputs allowed, producing corrupted allocation state.
- **Impact:** Misallocation of portfolio cash, permitting over-allocation to one desk at the expense of others.
- **Remediation:** Clamped all inputs to `max(0.0, float(...))` and added strict numeric parsing with HTTP 400 error response on invalid input in `handle_capital_allocation`.
- **Regression Tests:** `tests/test_audit_security_and_invariants.py::test_capital_allocation_negative_clamping`, `test_dashboard_security_headers_and_token`.
- **Status:** **VERIFIED & FIXED**

---

### AUDIT-006: Unhandled `std::stod` Crash on Malformed Lines in C++ Scanner
- **Severity:** Low
- **Confidence:** High
- **Category:** Reliability / Exception Safety
- **Affected Files:** `cpp/scanner.cpp` (lines 28-35)
- **Affected Workflow:** Native C++ high-performance CSV market scanner.
- **Evidence:** Direct invocations of `std::stod(s)` without checking for empty string tokens or catching `std::invalid_argument` / `std::out_of_range`.
- **Trigger Conditions:** Market data feed emitting trailing commas, blank rows, or corrupted ticker data.
- **Expected vs Actual:**
  - *Expected:* Graceful row skipping on malformed tokens.
  - *Actual:* Process termination due to unhandled C++ exception.
- **Impact:** Scanner abort requiring manual restart.
- **Remediation:** Added empty string checks (`s.empty() ? 0.0 : std::stod(s)`) and wrapped parsing in `try/catch (...) { continue; }`.
- **Regression Tests:** Code inspection and syntax validation.
- **Status:** **VERIFIED & FIXED**

---

### AUDIT-007: Dockerfile Loopback Host Binding Preventing External Connectivity
- **Severity:** Low
- **Confidence:** High
- **Category:** Infrastructure / Deployment Configuration
- **Affected Files:** `docker/Dockerfile` (line 18)
- **Affected Workflow:** Containerized application deployment.
- **Evidence:** `ENV APP_HOST=127.0.0.1` prevented Docker container from accepting connections forwarded from the host port.
- **Trigger Conditions:** Running `docker run -p 5000:5000 tradng-ai` without overriding environment variables.
- **Expected vs Actual:**
  - *Expected:* Container binds to `0.0.0.0` so forwarded ports route correctly.
  - *Actual:* Container bound only to container-internal loopback `127.0.0.1`.
- **Impact:** Dashboard inaccessible when run as a standalone Docker container.
- **Remediation:** Changed `ENV APP_HOST=0.0.0.0 APP_PORT=5000` while keeping container-internal healthcheck querying `http://127.0.0.1:5000/health`.
- **Regression Tests:** Configuration validation.
- **Status:** **VERIFIED & FIXED**
