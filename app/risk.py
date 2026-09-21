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
            self.cfg["execution"].get("short_margin_pct", 0.25),
        )["equity"]

    def approve(self, p, qty):
        if qty <= 0 or p.get("confidence", 0) < 60:
            return "REJECT"

        if p.get("risk_reward", 0) < self.cfg["risk"]["min_risk_reward"]:
            return "REJECT"

        if p.get("action") not in {"BUY", "SHORT"}:
            return "REJECT"

        if p["action"] == "SHORT" and not self.cfg.get("allow_shorts", True):
            return "REJECT"

        positions = self.db.positions()

        if any(x["symbol"] == p["symbol"] for x in positions):
            return "REJECT"

        equity = self.equity()

        if equity <= 0:
            return "REJECT"

        account = self.db.account()

        margin_pct = self.cfg["execution"].get("short_margin_pct", 0.25)

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
            float(account["cash"]) - reserved_margin,
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

        if (
            peak > 0
            and (peak - equity) / peak
            >= self.cfg["risk"]["emergency_drawdown_pct"]
        ):
            return "REJECT"

        max_exposure = (
            equity
            * self.cfg["risk"]["max_portfolio_invested_pct"]
        )

        current_exposure = sum(
            float(x["qty"]) * float(x["current_price"])
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
                float(x["qty"]) * float(x["current_price"])
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

        account = self.db.account()

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
            return False, "maximum drawdown reached"

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