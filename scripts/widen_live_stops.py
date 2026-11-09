#!/usr/bin/env python3
"""
Widens stop losses of active intraday positions to ensure they have at least
0.8% minimum breathing room from entry price, preventing noise stop-outs.
"""
import sqlite3
import sys

def widen_stops(db_path="data/trader.db"):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT symbol, side, entry_price, stop_loss FROM positions WHERE UPPER(product_type)='INTRADAY'")
    positions = cur.fetchall()
    
    updated = 0
    for sym, side, entry, sl in positions:
        entry = float(entry)
        sl = float(sl)
        min_buffer = entry * 0.008
        if side == "LONG":
            safe_sl = round(entry - min_buffer, 2)
            if sl > safe_sl:
                print(f"[WIDEN STOP] {sym} (LONG): Widening SL from ₹{sl:.2f} to ₹{safe_sl:.2f} (0.8% room)")
                cur.execute("UPDATE positions SET stop_loss=? WHERE symbol=?", (safe_sl, sym))
                updated += 1
        elif side == "SHORT":
            safe_sl = round(entry + min_buffer, 2)
            if sl < safe_sl:
                print(f"[WIDEN STOP] {sym} (SHORT): Widening SL from ₹{sl:.2f} to ₹{safe_sl:.2f} (0.8% room)")
                cur.execute("UPDATE positions SET stop_loss=? WHERE symbol=?", (safe_sl, sym))
                updated += 1
                
    conn.commit()
    conn.close()
    print(f"Updated {updated} positions.")

if __name__ == "__main__":
    db_file = sys.argv[1] if len(sys.argv) > 1 else "data/trader.db"
    widen_stops(db_file)

