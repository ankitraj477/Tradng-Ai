from .accounting import portfolio_metrics


class PortfolioManager:
    def __init__(self, db, cfg):
        self.db = db
        self.cfg = cfg

    def state(self):
        account = self.db.account()
        positions = self.db.positions()

        metrics = portfolio_metrics(
            account,
            positions,
            self.cfg["execution"].get(
                "short_margin_pct",
                0.25,
            ),
        )

        return (
            account,
            positions,
            metrics["long_value"],
            metrics["short_notional"],
            metrics["equity"],
        )

    def metrics(self):
        account = self.db.account()

        return portfolio_metrics(
            account,
            self.db.positions(),
            self.cfg["execution"].get(
                "short_margin_pct",
                0.25,
            ),
        )

    def size(self, proposal):
        (
            account,
            positions,
            long_value,
            short_notional,
            equity,
        ) = self.state()

        if equity <= 0:
            return 0

        risk_cash = (
            equity
            * self.cfg["risk"]["max_position_risk_pct"]
        )

        per_share = max(
            abs(
                proposal["price"]
                - proposal["stop_loss"]
            ),
            0.01,
        )

        qty_by_risk = int(
            risk_cash / per_share
        )

        max_exposure = (
            equity
            * self.cfg["risk"]["max_portfolio_invested_pct"]
        )

        remaining_exposure = max(
            0,
            max_exposure
            - (long_value + short_notional),
        )

        qty_by_portfolio = int(
            remaining_exposure
            / proposal["price"]
        )

        # Use canonical available cash, which already
        # excludes reserved short margin.
        available_cash = self.metrics()["available_cash"]

        if proposal.get("action") == "BUY":
            qty_by_cash = int(
                available_cash
                / proposal["price"]
            )

        elif proposal.get("action") == "SHORT":
            margin_pct = self.cfg["execution"].get(
                "short_margin_pct",
                0.25,
            )

            qty_by_cash = int(
                available_cash
                / (proposal["price"] * margin_pct)
            )

        else:
            return 0

        return max(
            0,
            min(
                qty_by_risk,
                qty_by_portfolio,
                qty_by_cash,
            ),
        )