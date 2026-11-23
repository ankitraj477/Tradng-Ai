#!/usr/bin/env python3
"""
Tradng-Ai ₹100,000 (1 Lakh) Institutional Capital Ledger Reset & Transition Script
Restores the proven institutional framework:
- ₹100,000.00 Starting Capital & Liquid Cash
- ₹5,000,000.00 Target Capital (Institutional Compounding Goal)
- Multi-Desk Balanced Allocation:
  - Swing Trading Desk (CNC): 40.0%
  - F&O Defined-Risk Options Desk: 35.0%
  - Intraday Institutional Desk (MIS): 25.0%
- Archives current database safely and cleans stale paper positions.
"""
import os
import shutil
import sqlite3
import json
from datetime import datetime, timezone

def reset_database(db_path: str = "data/trader.db"):
    if not os.path.exists(db_path):
        print(f"[ERROR] Database {db_path} does not exist.")
        return False

    # 1. Safe archival
    dir_name = os.path.dirname(db_path) or "."
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = os.path.join(dir_name, f"trader_archive_pre_100k_{ts}.db")
    print(f"[ARCHIVE] Creating backup copy at {archive_path}...")
    shutil.copy2(db_path, archive_path)

    # 2. Reset ledger tables
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    print("[RESET] Wiping stale paper positions, orders, brackets, decisions...")
    cur.execute("DELETE FROM positions;")
    cur.execute("DELETE FROM trades;")
    cur.execute("DELETE FROM orders;")
    cur.execute("DELETE FROM bracket_orders;")
    cur.execute("DELETE FROM decisions;")
    cur.execute("DELETE FROM daily_state;")
    cur.execute("DELETE FROM stop_updates;")
    cur.execute("DELETE FROM events;")
    cur.execute("DELETE FROM equity_curve;")

    print("[RESET] Re-initializing account to ₹100,000.00 cash & ₹5,000,000.00 target...")
    cur.execute("""
        UPDATE account 
        SET cash = 100000.0,
            starting_capital = 100000.0,
            target_capital = 5000000.0,
            peak_value = 100000.0,
            updated_at = ?
        WHERE id = 1;
    """, (now_iso,))

    # Seed initial equity curve point
    try:
        cur.execute("""
            INSERT INTO equity_curve (time, equity, cash, unrealized)
            VALUES (?, 100000.0, 100000.0, 0.0);
        """, (now_iso,))
    except Exception:
        pass

    # Ensure system_settings has balanced Multi-Desk allocation
    print("[RESET] Setting capital allocation to Institutional Multi-Desk (40% Swing, 35% F&O, 25% Intraday)...")
    alloc_json = json.dumps({"intraday": 25.0, "swing": 40.0, "fno": 35.0})
    cur.execute("""
        INSERT OR REPLACE INTO system_settings (key, value)
        VALUES ('capital_allocation', ?);
    """, (alloc_json,))
    cur.execute("""
        INSERT OR REPLACE INTO system_settings (key, value)
        VALUES ('auto_trading_enabled', '1');
    """)

    conn.commit()
    cur.execute("VACUUM;")
    conn.commit()

    # Verification
    cur.execute("SELECT id, cash, starting_capital, target_capital, peak_value FROM account WHERE id=1")
    acc = cur.fetchone()
    cur.execute("SELECT count(*) FROM positions")
    pos_count = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM trades")
    trade_count = cur.fetchone()[0]
    cur.execute("SELECT value FROM system_settings WHERE key='capital_allocation'")
    saved_alloc = cur.fetchone()[0]
    conn.close()

    print("\n" + "=" * 60)
    print("       TRADNG-AI ₹100,000 INSTITUTIONAL CAPITAL LEDGER INITIALIZED")
    print("=" * 60)
    print(f" Account ID:         {acc[0]}")
    print(f" Liquid Cash:        ₹{acc[1]:,.2f}")
    print(f" Starting Capital:   ₹{acc[2]:,.2f}")
    print(f" Target Capital:     ₹{acc[3]:,.2f} (50x Goal)")
    print(f" Peak Value:         ₹{acc[4]:,.2f}")
    print(f" Active Positions:   {pos_count}")
    print(f" Total Trades:       {trade_count}")
    print(f" Capital Allocation: {saved_alloc}")
    print("=" * 60 + "\n")
    return True

if __name__ == "__main__":
    reset_database()
