"""
Maintenance script: Cancel and clear unvalidated pending FNO After-Market Orders.
"""
from pathlib import Path
import sqlite3

def clean_fno_pending():
    db_path = Path("data/trader.db")
    if not db_path.exists():
        print("data/trader.db not found")
        return

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("DELETE FROM orders WHERE product_type='FNO' AND status='PENDING'")
    count = cur.rowcount
    conn.commit()
    conn.close()
    print(f"Cleared {count} pending FNO orders.")

if __name__ == "__main__":
    clean_fno_pending()
