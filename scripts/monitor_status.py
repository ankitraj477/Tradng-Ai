#!/usr/bin/env python3
"""
Tradng-Ai Live Performance Monitor & Gamification Scorecard Auditor
"""
import urllib.request
import json

def audit():
    try:
        url = "http://127.0.0.1:5000/api/state"
        req = urllib.request.urlopen(url, timeout=5)
        data = json.loads(req.read().decode("utf-8"))
    except Exception as e:
        print(f"Error connecting to dashboard API: {e}")
        return

    portfolio = float(data.get("portfolio", 0.0))
    starting = float(data.get("starting_capital", 1000.0))
    daily_pnl = float(data.get("daily_pnl", 0.0))
    daily_pct = (daily_pnl / starting) * 100 if starting > 0 else 0.0

    # User Gamification Points Table
    # 0%: -1 pt | 1%: 0 pt | 2%: +1 pt | 3%: +2 pt | 4%: +3 pt | 5%: +4 pt | 5+%: +5 pt
    if daily_pct >= 5.0:
        points = 5
        grade = "🏆 S-TIER (TARGET EXCEEDED)"
    elif daily_pct >= 4.0:
        points = 3
        grade = "🟢 A-TIER (STRONG PROFIT)"
    elif daily_pct >= 3.0:
        points = 2
        grade = "🟢 B-TIER (SOLID ALPHA)"
    elif daily_pct >= 2.0:
        points = 1
        grade = "🟡 C-TIER (POSITIVE)"
    elif daily_pct >= 1.0:
        points = 0
        grade = "⚪ D-TIER (PAR / BREAKEVEN)"
    elif daily_pct >= 0.0:
        points = -1
        grade = "🟠 FLAT (-1 POINT)"
    elif daily_pct >= -1.0:
        points = -2
        grade = "🔴 MINOR LOSS (-2 POINTS)"
    elif daily_pct >= -2.0:
        points = -3
        grade = "🔴 LOSS (-3 POINTS)"
    elif daily_pct >= -3.0:
        points = -4
        grade = "🔴 HEAVY LOSS (-4 POINTS)"
    elif daily_pct >= -4.0:
        points = -5
        grade = "⛔ CRITICAL LOSS (-5 POINTS)"
    else:
        points = -6
        grade = "🚨 SEVERE LOSS (-6 POINTS)"

    print("=" * 65)
    print("       TRADNG-AI LIVE PERFORMANCE & SCORECARD MONITOR")
    print("=" * 65)
    print(f" Total Net Equity:    ₹{portfolio:,.2f}")
    print(f" Starting Capital:    ₹{starting:,.2f}")
    print(f" Available Cash:      ₹{float(data.get('cash', 0.0)):,.2f}")
    print(f" Today's Net P&L:     {'+' if daily_pnl >= 0 else ''}₹{daily_pnl:,.2f} ({'+' if daily_pct >= 0 else ''}{daily_pct:.2f}%)")
    print(f" 5% Daily Target:     ₹{starting * 0.05:,.2f} ({'ACHIEVED' if daily_pct >= 5.0 else f'₹{(starting * 0.05) - daily_pnl:.2f} remaining'})")
    print(f" Daily Points Score:  {'+' if points > 0 else ''}{points} pts [{grade}]")
    print("-" * 65)

    positions = data.get("positions", [])
    print(f" Active Open Positions ({len(positions)}):")
    if not positions:
        print("   (No active positions. Cash is liquid and waiting for high-conviction setups)")
    for p in positions:
        sym = p.get("symbol")
        side = p.get("side")
        qty = p.get("qty")
        entry = float(p.get("entry_price", 0.0))
        curr = float(p.get("current_price", entry))
        sl = float(p.get("stop_loss", 0.0))
        target = float(p.get("target", 0.0))
        pnl = float(p.get("pnl", 0.0))
        pct = float(p.get("pnl_pct", 0.0))
        status = "🛡️ RISK-FREE" if (side == "LONG" and sl >= entry) else "⏳ ACTIVE"
        print(f"   • {sym} ({side} x{qty}) Entry: ₹{entry:.2f} | Curr: ₹{curr:.2f} | PnL: {'+' if pnl >= 0 else ''}₹{pnl:.2f} ({'+' if pct >= 0 else ''}{pct:.2f}%) | SL: ₹{sl:.2f} | Target: ₹{target:.2f} [{status}]")

    trades = data.get("trades", [])
    print("-" * 65)
    print(f" Completed Trades Today ({len(trades)}):")
    for t in trades[:5]:
        sym = t.get("symbol")
        side = t.get("side")
        qty = t.get("qty")
        entry = float(t.get("entry_price", 0.0))
        exit_px = float(t.get("exit_price", 0.0))
        pnl = float(t.get("pnl", 0.0))
        pct = float(t.get("pnl_pct", 0.0))
        reason = t.get("exit_reason", "")
        print(f"   • {sym} ({side} x{qty}) Entry: ₹{entry:.2f} ➔ Exit: ₹{exit_px:.2f} | Net: {'+' if pnl >= 0 else ''}₹{pnl:.2f} ({pct:.2f}%) [{reason}]")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    audit()
