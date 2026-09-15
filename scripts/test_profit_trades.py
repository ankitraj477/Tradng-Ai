import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engine import TradingEngine


engine = TradingEngine()

symbol = "ITC.NS"
qty = 1

# Simulated favorable price movements.
profit_moves = [
    0.01,  # +1%
    0.02,  # +2%
    0.03,  # +3%
    0.04,  # +4%
    0.05,  # +5%
]

print("\n=== 10 PROFITABLE PAPER TRADE TEST ===")

starting_cash = engine.db.account()["cash"]

print(f"Starting cash: ₹{starting_cash:.2f}\n")


for i in range(1, 11):

    market_price = float(
        engine.provider.quote(symbol)["price"]
    )

    move = profit_moves[(i - 1) // 2]

    # ---------------------------------
    # LONG
    # ---------------------------------

    if i % 2 == 1:

        signal = {
            "symbol": symbol,
            "action": "BUY",
            "price": market_price,
            "confidence": 90,
            "strategy": "TEST_PROFIT_LONG",
            "stop_loss": market_price * 0.98,
            "target": market_price * (1 + move),
            "risk_reward": 2.0,
            "sector": None,
            "atr": 5.0,
        }

        opened = engine.exec.buy(
            signal,
            qty,
            "TEST",
        )

        if opened:

            # Simulate market moving UP.
            exit_price = market_price * (1 + move)

            closed = engine.exec.close(
                symbol,
                exit_price,
                f"TEST_PROFIT_{move*100:.0f}PCT",
                "TEST",
            )

        else:
            closed = False

        side = "LONG"

    # ---------------------------------
    # SHORT
    # ---------------------------------

    else:

        signal = {
            "symbol": symbol,
            "action": "SHORT",
            "price": market_price,
            "confidence": 90,
            "strategy": "TEST_PROFIT_SHORT",
            "stop_loss": market_price * 1.02,
            "target": market_price * (1 - move),
            "risk_reward": 2.0,
            "sector": None,
            "atr": 5.0,
        }

        opened = engine.exec.short(
            signal,
            qty,
            "TEST",
        )

        if opened:

            # Simulate market moving DOWN.
            exit_price = market_price * (1 - move)

            closed = engine.exec.close(
                symbol,
                exit_price,
                f"TEST_PROFIT_{move*100:.0f}PCT",
                "TEST",
            )

        else:
            closed = False

        side = "SHORT"

    latest = engine.db.trades(1)

    pnl = (
        latest[0]["pnl"]
        if latest
        else 0
    )

    print(
        f"Trade {i:02d} | "
        f"{side:5s} | "
        f"Move={move*100:.0f}% | "
        f"OPEN={'OK' if opened else 'FAIL'} | "
        f"CLOSE={'OK' if closed else 'FAIL'} | "
        f"P&L=₹{pnl:.2f}"
    )


print("\n=== FINAL RESULT ===")

ending_cash = engine.db.account()["cash"]

print(f"Starting cash : ₹{starting_cash:.2f}")
print(f"Ending cash   : ₹{ending_cash:.2f}")
print(f"Net change    : ₹{ending_cash-starting_cash:.2f}")

print("\nOPEN POSITIONS:")
print(engine.db.positions())

print("\nLAST 10 TRADES:")

trades = engine.db.trades(10)

for trade in trades:
    print(
        f"#{trade['id']} "
        f"{trade['side']:5s} "
        f"Entry=₹{trade['entry_price']:.2f} "
        f"Exit=₹{trade['exit_price']:.2f} "
        f"P&L=₹{trade['pnl']:.2f} "
        f"({trade['pnl_pct']:.2f}%)"
    )


profitable = sum(
    1
    for trade in trades
    if trade["pnl"] > 0
)

print(f"\nProfitable trades: {profitable}/10")

if profitable == 10 and not engine.db.positions():
    print("\n✅ PROFIT ACCOUNTING TEST PASSED")
else:
    print("\n❌ PROFIT ACCOUNTING TEST FAILED")