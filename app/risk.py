class RiskManager:
    def __init__(self, db, cfg):
        self.db = db
        self.cfg = cfg

    def equity(self):
        from .accounting import portfolio_metrics

        a = self.db.account()

        return portfolio_metrics(
            a,
            self.db.positions(),
            self.cfg.get("execution", {}).get("short_margin_pct", 0.25),
        )["equity"]

    def approve(self, p, qty, regime_ctx=None):
        """
        Risk gate for trade proposals.
        BUG-009: Now accepts optional regime_ctx to enforce allowed_sides and size_multiplier.
        BUG-025: Handles NULL stop_loss gracefully.
        """
        if qty <= 0 or p.get("confidence", 0) < 60:
            return "REJECT"

        if p.get("risk_reward", 0) < self.cfg["risk"]["min_risk_reward"]:
            return "REJECT"

        # BUG-009: Enforce regime allowed_sides
        if regime_ctx:
            allowed_sides = regime_ctx.get("allowed_sides", ["LONG", "SHORT"])
            action_side = "LONG" if p.get("action") == "BUY" else "SHORT"
            if action_side not in allowed_sides:
                return "REJECT"
            # BUG-009: Reject if regime says no trading (size_multiplier == 0)
            if regime_ctx.get("size_multiplier", 1.0) <= 0:
                return "REJECT"

            # News Event Risk Gate (Blocks buying on fraud probes, regulatory actions)
            if regime_ctx.get("news_items"):
                from .event_classifier import EventClassifier
                clf = EventClassifier()
                news_risk = clf.evaluate_risk_filter(p["symbol"], regime_ctx["news_items"])
                if news_risk.get("block_entry") and p.get("action") == "BUY":
                    if hasattr(self, "db") and self.db:
                        self.db.log("WARN", f"News Risk Filter: Blocked entry for {p['symbol']} - {news_risk.get('reason')}")
                    return "REJECT"

        if "target" in p and "price" in p and p.get("target"):
            from .risk_engine import MinimumMoveGate
            # BUG-023: Pass configured cost model and map SHORT->SELL
            from .costs import CostModel
            cost_model = CostModel(self.cfg)
            move_gate = MinimumMoveGate(
                cost_multiplier=self.cfg.get("risk", {}).get("min_move_cost_multiplier", 1.5),
                cost_model=cost_model
            )
            # BUG-023: Map SHORT to SELL for proper STT calculation
            gate_action = "SELL" if p.get("action") == "SHORT" else p.get("action", "BUY")
            ok_move, _ = move_gate.check(p["price"], p["target"], p.get("stop_loss", p["price"]), gate_action)
            if not ok_move:
                return "REJECT"

        if p.get("action") not in {"BUY", "SHORT"}:
            return "REJECT"

        if p["action"] == "SHORT" and not self.cfg.get("allow_shorts", True):
            return "REJECT"

        positions = self.db.positions()

        if any(x["symbol"] == p["symbol"] for x in positions):
            return "REJECT"

        max_positions = self.cfg.get("market", {}).get("max_open_positions")
        if max_positions is not None and len(positions) >= int(max_positions):
            return "REJECT"

        equity = self.equity()

        if equity <= 0:
            return "REJECT"

        from .risk_engine import PortfolioHeatLimiter
        # BUG-025: Use explicit config key with proper default
        heat_limiter = PortfolioHeatLimiter(
            max_heat_pct=self.cfg.get("risk", {}).get("max_portfolio_heat_pct", 0.06),
            max_sector_pct=self.cfg.get("risk", {}).get("max_sector_exposure_pct", 0.40)
        )
        ok_heat, _ = heat_limiter.check(equity, positions, p, qty)
        if not ok_heat:
            return "REJECT"

        account = self.db.account() or {}

        margin_pct = self.cfg.get("execution", {}).get("short_margin_pct", 0.25)

        # Short margin already reserved by existing short positions
        # must not be reused for another trade.
        reserved_margin = sum(
            float(x["entry_price"])
            * int(x["qty"])
            * margin_pct
            for x in positions
            if x["side"] == "SHORT"
        )

        available_cash = max(
            0.0,
            float(account.get("cash", 0.0)) - reserved_margin,
        )

        if p["action"] == "BUY":
            required = p["price"] * qty
        else:
            required = p["price"] * qty * margin_pct

        if required > available_cash:
            return "REJECT"

        peak = float(
            account.get("peak_value", equity) or equity
        )

        emergency_dd = self.cfg.get("risk", {}).get("emergency_drawdown_pct", 0.20)
        if (
            peak > 0
            and (peak - equity) / peak
            >= emergency_dd
        ):
            return "REJECT"

        max_invested = self.cfg.get("risk", {}).get("max_portfolio_invested_pct", 0.80)
        max_exposure = (
            equity
            * max_invested
        )

        current_exposure = sum(
            float(x["qty"]) * float(x.get("current_price", x["entry_price"]))
            for x in positions
        )

        new_exposure = (
            current_exposure
            + p["price"] * qty
        )

        if new_exposure > max_exposure:
            return "REJECT"

        sector = p.get("sector")

        if sector and sector != "Unknown":
            sector_exposure = sum(
                float(x["qty"]) * float(x.get("current_price", x["entry_price"]))
                for x in positions
                if x.get("sector") == sector
            )

            sector_exposure += p["price"] * qty

            sector_limit = (
                equity
                * self.cfg["risk"]["max_sector_exposure_pct"]
            )

            if sector_exposure > sector_limit:
                return "REJECT"

        return "APPROVE"

    def trading_allowed(self):
        risk = self.cfg.get("risk", {})

        if risk.get("kill_switch", False):
            return False, "kill switch enabled"

        account = self.db.account() or {}

        from .accounting import portfolio_metrics

        metrics = portfolio_metrics(
            account,
            self.db.positions(),
            self.cfg["execution"].get("short_margin_pct", 0.25),
        )

        peak = float(
            account.get(
                "peak_value",
                metrics["equity"],
            )
            or metrics["equity"]
        )

        if (
            peak > 0
            and (peak - metrics["equity"]) / peak
            >= float(risk.get("max_drawdown_pct", 1.0))
        ):
            # BUG-026: Log drawdown lockout with explicit alert
            self.db.log(
                "ERROR",
                f"DRAWDOWN LOCKOUT: Equity {metrics['equity']:.2f} vs peak {peak:.2f} "
                f"({(peak - metrics['equity']) / peak * 100:.1f}% drawdown). "
                f"Trading suspended. To reset: use /api/kill-switch/reset or "
                f"manually update peak_value in the database."
            )
            return False, "maximum drawdown reached"

        # BUG-047: Use IST date for daily loss baseline
        from .market_hours import now_ist
        start_equity = self.db.day_start_equity(
            metrics["equity"]
        )

        if (
            start_equity > 0
            and (
                start_equity - metrics["equity"]
            ) / start_equity
            >= float(
                risk.get(
                    "daily_loss_limit_pct",
                    1.0,
                )
            )
        ):
            return False, "daily loss limit reached"

        return True, "allowed"