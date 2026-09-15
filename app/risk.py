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

        # Do not allow duplicate positions in the same symbol.
        if any(x["symbol"] == p["symbol"] for x in positions):
            return "REJECT"

        equity = self.equity()

        if equity <= 0:
            return "REJECT"

        a = self.db.account()

        margin_pct = self.cfg["execution"].get("short_margin_pct", 0.25)

        if p["action"] == "BUY":
            required = p["price"] * qty
        else:
            required = p["price"] * qty * margin_pct

        if required > a["cash"]:
            return "REJECT"

        # Emergency drawdown protection.
        if (
            a["peak_value"] > 0
            and (a["peak_value"] - equity) / a["peak_value"]
            >= self.cfg["risk"]["emergency_drawdown_pct"]
        ):
            return "REJECT"

        # Global portfolio exposure limit.
        max_exposure = (
            equity * self.cfg["risk"]["max_portfolio_invested_pct"]
        )

        current = sum(
            x["qty"] * x["current_price"]
            for x in positions
        )

        new_exposure = current + p["price"] * qty

        if new_exposure > max_exposure:
            return "REJECT"

        # Sector concentration.
        #
        # "Unknown" is not treated as a real sector.
        # When sector metadata is unavailable, the global
        # portfolio exposure limit above still applies.
        sector = p.get("sector")

        if sector and sector != "Unknown":
            sector_exp = sum(
                x["qty"] * x["current_price"]
                for x in positions
                if x.get("sector") == sector
            )

            sector_exp += p["price"] * qty

            sector_limit = (
                equity * self.cfg["risk"]["max_sector_exposure_pct"]
            )

            if sector_exp > sector_limit:
                return "REJECT"

        return "APPROVE"

    def trading_allowed(self):
        risk = self.cfg.get("risk", {})

        if risk.get("kill_switch", False):
            return False, "kill switch enabled"

        a = self.db.account()

        from .accounting import portfolio_metrics

        m = portfolio_metrics(
            a,
            self.db.positions(),
            self.cfg["execution"].get("short_margin_pct", 0.25),
        )

        peak = float(
            a.get("peak_value", m["equity"]) or m["equity"]
        )

        if (
            peak > 0
            and (peak - m["equity"]) / peak
            >= float(risk.get("max_drawdown_pct", 1.0))
        ):
            return False, "maximum drawdown reached"

        start_equity = self.db.day_start_equity(m["equity"])

        if (
            start_equity > 0
            and (start_equity - m["equity"]) / start_equity
            >= float(risk.get("daily_loss_limit_pct", 1.0))
        ):
            return False, "daily loss limit reached"

        return True, "allowed"