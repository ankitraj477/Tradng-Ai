"""
F&O Execution Engine for Defined-Risk Index Spreads.
Handles margin allocation, multi-leg recording, and option decay P&L.
"""
from datetime import datetime, timezone
from ..exchange_rules import round_to_tick


class FNOExecution:
    def __init__(self, db, cfg=None):
        self.db = db
        self.cfg = cfg or {}

    def open_spread(self, proposal, lots=1, force_fill=False) -> bool:
        """Open a defined-risk option spread or condor. Queues AMO if market is closed."""
        if hasattr(proposal, "__dict__") and not isinstance(proposal, dict):
            underlying = getattr(proposal, "underlying", "NIFTY")
            strat = getattr(proposal, "strategy_name", "Iron_Condor").replace(" ", "_")
            exp = getattr(proposal, "expiry_date", "Weekly")
            p_dict = {
                "symbol": f"{underlying}_{strat}_{exp}",
                "price": getattr(proposal, "net_credit", 40.0),
                "target": getattr(proposal, "profit_target", 20.0),
                "stop_loss": getattr(proposal, "stop_loss", 80.0),
                "lot_size": getattr(proposal, "lot_size", 25) * lots,
                "margin_required": getattr(proposal, "max_loss", 2500.0) * lots,
                "strategy": getattr(proposal, "strategy_name", "Iron Condor"),
                "confidence": 85,
                "strike_price": getattr(proposal, "short_put", 0.0),
                "option_type": "CONDOR" if "Condor" in strat else "SPREAD",
                "expiry_date": exp,
                "legs_info": f"Short Put: {getattr(proposal, 'short_put', 0)}, Short Call: {getattr(proposal, 'short_call', 0)}"
            }
            proposal = p_dict

        symbol = proposal["symbol"]
        qty = int(proposal.get("lot_size", 25))
        margin_req = float(proposal.get("margin_required", 2500.0))
        entry_credit = round_to_tick(float(proposal["price"]))
        sl = round_to_tick(proposal["stop_loss"]) if proposal.get("stop_loss") is not None else None
        tp = round_to_tick(proposal["target"]) if proposal.get("target") is not None else None

        from ..market_hours import market_open
        enforce_hours = (
            self.cfg.get("execution", {}).get("enforce_market_hours", False)
            or self.cfg.get("enforce_market_hours", False)
            or self.cfg.get("live_data", False)
        )

        # Off-market hours: Queue as After-Market Order (AMO)
        if enforce_hours and not force_fill and not market_open():
            self.db.add_order({
                "symbol": symbol,
                "action": "SELL",
                "side": "SHORT",
                "qty": qty,
                "price": entry_credit,
                "stop_loss": sl,
                "target": tp,
                "product_type": "FNO",
                "order_type": "AMO",
                "status": "PENDING",
                "strategy": proposal.get("strategy", "Iron Condor")
            })
            self.db.log(
                "INFO",
                f"[F&O AMO PLACED] Market CLOSED. Placed F&O After-Market Order (AMO) for {proposal.get('strategy')} on {symbol} "
                f"x{qty} @ ₹{entry_credit:.2f} credit. Will execute at 09:15 AM IST."
            )
            return True

        with self.db.conn() as c:
            row = c.execute("SELECT * FROM account WHERE id=1").fetchone()
            if not row:
                now_str = datetime.now(timezone.utc).isoformat()
                c.execute("INSERT OR IGNORE INTO account VALUES(1, 100000.0, 100000.0, 200000.0, 100000.0, ?)", (now_str,))
                row = c.execute("SELECT * FROM account WHERE id=1").fetchone()
            acc = dict(row) if row else {"cash": 0.0, "initial_capital": 0.0}
            short_margin_pct = float(self.cfg.get("execution", {}).get("short_margin_pct", 0.25))
            open_pos = [dict(r) for r in c.execute("SELECT * FROM positions").fetchall()]
            reserved = sum(float(x['entry_price']) * float(x['qty']) * short_margin_pct for x in open_pos if x['side'] == 'SHORT')
            avail = max(0.0, float(acc.get('cash', 0.0)) - reserved)
            if margin_req > avail:
                return False

            c.execute(
                """INSERT INTO positions(symbol, side, qty, entry_price, current_price, stop_loss, target,
                                         strategy, confidence, opened_at, sector, atr, entry_cost, target_step,
                                         product_type, strike_price, option_type, expiry_date, legs_info)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(sleeve, symbol) DO UPDATE SET
                   current_price=excluded.current_price""",
                (
                    symbol, "SELL", qty, entry_credit, entry_credit,
                    sl, tp,
                    proposal.get("strategy"), proposal.get("confidence", 80),
                    datetime.now(timezone.utc).isoformat(), "INDICES",
                    0.0, margin_req, 0.0, "FNO",
                    proposal.get("strike_price", 0.0), proposal.get("option_type", ""),
                    proposal.get("expiry_date", ""), proposal.get("legs_info", "")
                )
            )
            # Reserve margin in cash
            c.execute("UPDATE account SET cash=cash-?, updated_at=? WHERE id=1",
                      (margin_req, datetime.now(timezone.utc).isoformat()))

        # Record executed order in orders table
        self.db.add_order({
            "symbol": symbol,
            "action": "SELL",
            "side": "SHORT",
            "qty": qty,
            "price": entry_credit,
            "stop_loss": sl,
            "target": tp,
            "product_type": "FNO",
            "order_type": "REGULAR",
            "status": "FILLED",
            "strategy": proposal.get("strategy", "Iron Condor")
        })

        self.db.log(
            "INFO",
            f"FNO OPEN {proposal['strategy']} {symbol} x{qty} (Credit Collected: ₹{entry_credit:.2f}/sh, Margin: ₹{margin_req:.2f})"
        )
        return True

    def close(self, symbol: str, current_premium: float, reason: str) -> bool:
        """Close an option spread and release margin + P&L."""
        current_premium = round_to_tick(float(current_premium))
        with self.db.conn() as c:
            row = c.execute("SELECT * FROM positions WHERE symbol=? AND UPPER(product_type)='FNO'", (symbol,)).fetchone()
            if not row:
                return False
            p = dict(row)
            qty = p["qty"]
            entry_credit = float(p["entry_price"])

            # In option selling: Profit = (Entry Credit - Current Premium) * Qty
            gross_pnl = round((entry_credit - current_premium) * qty, 2)
            fees = 50.0  # F&O exchange turnover fee + STT + brokerage
            net_pnl = round(gross_pnl - fees, 2)

            # Retrieve exact margin reserved on open from entry_cost (fallback to 2500.0)
            margin_req = float(p.get("entry_cost") or 2500.0)
            capital_released = margin_req + net_pnl

            pnl_pct = round((net_pnl / margin_req) * 100, 2) if margin_req > 0 else 0.0

            c.execute(
                """INSERT INTO trades(symbol, action, side, entry_price, exit_price, qty, capital, stop_loss, target,
                                     holding_seconds, pnl, pnl_pct, strategy, confidence, regime, entry_reason,
                                     exit_reason, risk_decision, created_at, product_type, strike_price,
                                     option_type, expiry_date)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    symbol, "BUY_TO_CLOSE", "SELL", entry_credit, current_premium, qty, margin_req,
                    p.get("stop_loss"), p.get("target"), 0.0, net_pnl, pnl_pct,
                    p.get("strategy"), p.get("confidence"), "Index Options", f"{p.get('strategy', 'F&O Spread')} ({symbol})",
                    reason, "APPROVED", datetime.now(timezone.utc).isoformat(), "FNO",
                    p.get("strike_price", 0.0), p.get("option_type", ""), p.get("expiry_date", "")
                )
            )
            c.execute("DELETE FROM positions WHERE symbol=?", (symbol,))
            c.execute("UPDATE account SET cash=cash+?, updated_at=? WHERE id=1",
                      (max(0.0, capital_released), datetime.now(timezone.utc).isoformat()))

        self.db.log(
            "INFO",
            f"FNO CLOSE {symbol} Premium: ₹{current_premium:.2f} (Entry: ₹{entry_credit:.2f}) "
            f"Net P&L: ₹{net_pnl:.2f} ({pnl_pct:+.2f}%) Reason: {reason}"
        )
        return True


FnoExecution = FNOExecution
