import atexit, os, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False); _tmp.close()
os.environ.setdefault("DATABASE_PATH", _tmp.name)
def _safe_unlink(p):
    try:
        Path(p).unlink(missing_ok=True)
    except OSError:
        pass

atexit.register(_safe_unlink, _tmp.name)

from app.engine import TradingEngine

print("\n=== PAPER TRADE EXECUTION TEST ===")
engine = TradingEngine()
if Path(engine.db.path).resolve() == (ROOT / "data" / "trader.db").resolve():
    sys.exit("Refusing to run on default trader.db")

symbol = "ITC.NS"

# Get current demo price
quote = engine.provider.quote(symbol)
price = float(quote["price"])

print(f"Symbol : {symbol}")
print(f"Price  : ₹{price:.2f}")

# Artificial test signal.
# This bypasses AI decision-making ONLY for this test.
signal = {
    "symbol": symbol,
    "action": "BUY",
    "price": price,
    "confidence": 90,
    "strategy": "TEST",
    "stop_loss": price * 0.98,
    "target": price * 1.04,
    "risk_reward": 2.0,
    "sector": None,
}

qty = 1

print(f"Quantity: {qty}")
print("Sending paper BUY...\n")

result = engine.exec.buy(
    signal,
    qty,
    "TEST",
)

print("EXECUTION RESULT:", result)

print("\n=== DATABASE AFTER BUY ===")
print("ACCOUNT:", engine.db.account())
print("POSITIONS:", engine.db.positions())
print("TRADES:", engine.db.trades(10))

if engine.db.positions():
    print("\n✅ PAPER TRADE EXECUTED SUCCESSFULLY")
else:
    print("\n❌ NO POSITION CREATED")