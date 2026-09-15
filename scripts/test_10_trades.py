import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engine import TradingEngine


engine = TradingEngine()

symbol = "ITC.NS"
qty = 1

print("\n=== 10 TRADE PAPER EXECUTION TEST ===")

for i in range(1, 11):
    price = float(engine.provider.quote(symbol)["price"])

    if i % 2 == 1:
        # LONG
        signal = {
            "symbol": symbol,
            "action": "BUY",
            "price": price,
            "confidence": 90,
            "strategy": "TEST_LONG",
            "stop_loss": price * 0.98,
            "target": price * 1.04,
            "risk_reward": 2.0,
            "sector": None,
            "atr": 5.0,
        }

        opened = engine.exec.buy(signal, qty, "TEST")

        if opened:
            position = engine.db.positions()[0]
            closed = engine.exec.close(
                symbol,
                position["current_price"],
                "TEST_LONG_EXIT",
                "TEST",
            )

        else:
            closed = False

        side = "LONG"

    else:
        # SHORT
        signal = {
            "symbol": symbol,
            "action": "SHORT",
            "price": price,
            "confidence": 90,
            "strategy": "TEST_SHORT",
            "stop_loss": price * 1.02,
            "target": price * 0.96,
            "risk_reward": 2.0,
            "sector": None,
            "atr": 5.0,
        }

        opened = engine.exec.short(signal, qty, "TEST")

        if opened:
            position = engine.db.positions()[0]
            closed = engine.exec.close(
                symbol,
                position["current_price"],
                "TEST_SHORT_EXIT",
                "TEST",
            )

        else:
            closed = False

        side = "SHORT"

    print(
        f"Trade {i:02d} | {side:5s} | "
        f"OPEN={'OK' if opened else 'FAIL'} | "
        f"CLOSE={'OK' if closed else 'FAIL'}"
    )


print("\n=== FINAL RESULT ===")

print("ACCOUNT:")
print(engine.db.account())

print("\nOPEN POSITIONS:")
print(engine.db.positions())

print("\nLAST 10 TRADES:")
trades = engine.db.trades(10)

for trade in trades:
    print(
        f"#{trade['id']} "
        f"{trade['symbol']} "
        f"{trade['side']} "
        f"P&L={trade['pnl']:.2f} "
        f"reason={trade['exit_reason']}"
    )

print("\nTOTAL TRADES:", len(trades))

if len(trades) == 10 and not engine.db.positions():
    print("\n✅ ALL 10 ROUND-TRIP TRADES PASSED")
else:
    print("\n❌ 10-TRADE TEST FAILED")