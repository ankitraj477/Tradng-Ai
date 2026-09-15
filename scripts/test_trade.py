import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engine import TradingEngine

print("\n=== PAPER TRADE EXECUTION TEST ===")
engine = TradingEngine()

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