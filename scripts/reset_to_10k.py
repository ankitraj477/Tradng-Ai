#!/usr/bin/env python3
"""
Tradng-Ai ₹10,000 Capital Ledger Reset & Transition Script
Safely archives existing database and resets ledger to:
- ₹10,000.00 Starting Capital & Liquid Cash
- ₹50,000.00 Target Capital (5x Goal Milestone)
- 100% Intraday MIS Allocation for Day 1 Bootstrapping
- Clears stale paper positions, orders, and trade history for fresh execution.
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
    archive_path = os.path.join(dir_name, f"trader_archive_pre_10k_{ts}.db")
    print(f"[ARCHIVE] Creating backup copy at {archive_path}...")
    shutil.copy2(db_path, archive_path)

    # 2. Reset ledger tables
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    print("[RESET] Wiping active positions, trades, orders, brackets, decisions...")
    cur.execute("DELETE FROM positions;")
    cur.execute("DELETE FROM trades;")
    cur.execute("DELETE FROM orders;")
    cur.execute("DELETE FROM bracket_orders;")
    cur.execute("DELETE FROM decisions;")
    cur.execute("DELETE FROM daily_state;")
    cur.execute("DELETE FROM stop_updates;")
    cur.execute("DELETE FROM events;")
    cur.execute("DELETE FROM equity_curve;")

    print("[RESET] Re-initializing account to ₹10,000.00 cash & ₹50,000.00 target...")
    cur.execute("""
        UPDATE account 
        SET cash = 10000.0,
            starting_capital = 10000.0,
            target_capital = 50000.0,
            peak_value = 10000.0,
            updated_at = ?
        WHERE id = 1;
    """, (now_iso,))

    # Seed initial equity curve point
    try:
        cur.execute("""
            INSERT INTO equity_curve (time, equity, cash, unrealized)
            VALUES (?, 10000.0, 10000.0, 0.0);
        """, (now_iso,))
    except Exception:
        pass

    # Ensure system_settings has 100% Intraday allocation
    print("[RESET] Setting capital allocation to 100% Intraday MIS (Tier 1)...")
    alloc_json = json.dumps({"intraday": 100.0, "swing": 0.0, "fno": 0.0})
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
    print("       TRADNG-AI ₹10,000 CAPITAL LEDGER INITIALIZED")
    print("=" * 60)
    print(f" Account ID:         {acc[0]}")
    print(f" Liquid Cash:        ₹{acc[1]:,.2f}")
    print(f" Starting Capital:   ₹{acc[2]:,.2f}")
    print(f" Target Capital:     ₹{acc[3]:,.2f} (5x Goal)")
    print(f" Peak Value:         ₹{acc[4]:,.2f}")
    print(f" Active Positions:   {pos_count}")
    print(f" Total Trades:       {trade_count}")
    print(f" Capital Allocation: {saved_alloc}")
    print("=" * 60)
    return True

if __name__ == "__main__":
    import sys
    db_file = sys.argv[1] if len(sys.argv) > 1 else "data/trader.db"
    reset_database(db_file)

