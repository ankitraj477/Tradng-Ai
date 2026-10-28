---
name: desk-runner
description: Manage and diagnose Tradng-Ai multi-desk engines (Intraday MIS, Swing CNC, F&O Spreads) and dashboard services.
---

# Multi-Desk Engine Runner & Operations

Use this skill when launching, stopping, or diagnosing Tradng-Ai engine processes.

## Available Runners

1. **Unified Multi-Desk Engine & Dashboard**:
   Runs Intraday, Swing, F&O desks simultaneously in background threads and serves the Flask dashboard:
   ```bash
   python run.py --port 5000
   ```
   Add `--live` to connect live market feeds (e.g. yfinance live session).

2. **Isolated Single-Desk Runners**:
   - Intraday Desk (MIS): `python run_intraday.py`
   - Swing Trading Desk (CNC): `python run_swing.py`
   - Futures & Options Desk (F&O): `python run_fno.py`
   - Standalone Dashboard UI: `python run_dashboard.py`

3. **Background Service (Oracle Cloud VM / Linux Systemd)**:
   ```bash
   sudo systemctl status tradng-ai.service
   sudo journalctl -u tradng-ai.service -f
   ```

## Health Verification
Check the operational status endpoint:
```bash
curl http://127.0.0.1:5000/api/health
curl http://127.0.0.1:5000/api/status
```

## Running Operational Unit Tests
```bash
python -m pytest tests/test_operational.py tests/test_isolated_runners.py tests/test_multi_book_desks.py -v
```
