"""
Maintenance script: Cancel and clear unvalidated pending FNO After-Market Orders.
"""
from pathlib import Path
import sqlite3

import sys

def clean_fno_pending(order_ids=None):
    db_path = Path("data/trader.db")
    if not db_path.exists():
        print("data/trader.db not found")
        return

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    if order_ids:
        placeholders = ','.join('?' for _ in order_ids)
        cur.execute(f"DELETE FROM orders WHERE product_type='FNO' AND status='PENDING' AND id IN ({placeholders})", tuple(order_ids))
        count = cur.rowcount
        conn.commit()
        print(f"Cleared {count} specific pending FNO orders: {order_ids}")
    else:
        cur.execute("SELECT id, symbol, qty, price, created_at FROM orders WHERE product_type='FNO' AND status='PENDING'")
        rows = cur.fetchall()
        if not rows:
            print("No pending FNO orders found.")
        else:
            print(f"Found {len(rows)} pending FNO orders:")
            for r in rows:
                print(f"  ID {r[0]}: {r[1]} x{r[2]} @ {r[3]} ({r[4]})")
            print("To delete specific unvalidated orders, run: python scripts/clean_fno_orders.py <id1> <id2> ...")
    conn.close()

if __name__ == "__main__":
    ids = [int(a) for a in sys.argv[1:] if a.isdigit()]
    clean_fno_pending(order_ids=ids if ids else None)
