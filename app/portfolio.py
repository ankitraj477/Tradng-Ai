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

    def size(self, proposal, size_multiplier=1.0):
        (
            account,
            positions,
            long_value,
            short_notional,
            equity,
        ) = self.state()

        if equity <= 0:
            return 0

        is_hyper = bool(self.cfg.get("hyper_aggressive", False))
        is_micro = bool(equity <= 15000.0 or self.cfg.get("micro_account", False))
        if is_micro and is_hyper:
            max_positions = 1 if equity <= 2500.0 else 2
        else:
            max_positions = self.cfg.get("market", {}).get("max_open_positions")

        if max_positions is not None and len(positions) >= int(max_positions):
            return 0

        # In Hyper-Aggressive mode on micro/small capital (equity <= 15000), deploy cash across focused setups
        if is_hyper and is_micro:
            available_cash = self.metrics()["available_cash"]
            eff_slots = float(max_positions) if max_positions else 2.0
            slot_alloc = (equity * 0.90) / eff_slots
            max_trade_cap = min(available_cash * 0.88, slot_alloc)
            final_qty = max(0, int(max_trade_cap / proposal["price"]))
            sector = proposal.get("sector")
            if sector and sector != "Unknown" and "max_sector_exposure_pct" in self.cfg.get("risk", {}):
                current_sector = sum(
                    float(x["qty"]) * float(x.get("current_price", x.get("entry_price", 0)))
                    for x in positions
                    if x.get("sector") == sector
                )
                sector_limit = equity * self.cfg["risk"]["max_sector_exposure_pct"]
                qty_by_sector = int(max(0.0, sector_limit - current_sector) / proposal["price"])
                final_qty = min(final_qty, qty_by_sector)
            return final_qty

        # BUG-009: Scale position risk by regime size multiplier (e.g. 0.5 in High Volatility)
        mult = float(size_multiplier if size_multiplier is not None else 1.0)
        risk_cash = (
            equity
            * self.cfg["risk"]["max_position_risk_pct"]
            * max(0.0, mult)
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

        sector = proposal.get("sector")
        if sector and sector != "Unknown" and "max_sector_exposure_pct" in self.cfg.get("risk", {}):
            current_sector = sum(
                float(x["qty"]) * float(x.get("current_price", x.get("entry_price", 0)))
                for x in positions
                if x.get("sector") == sector
            )
            sector_limit = equity * self.cfg["risk"]["max_sector_exposure_pct"]
            qty_by_sector = int(max(0.0, sector_limit - current_sector) / proposal["price"])
        else:
            qty_by_sector = qty_by_risk

        final_qty = max(
            0,
            min(
                qty_by_risk,
                qty_by_portfolio,
                qty_by_cash,
                qty_by_sector,
            ),
        )
        min_notional = float(self.cfg.get("risk", {}).get("min_trade_notional", 0.0))
        if final_qty > 0 and min_notional > 0 and (final_qty * proposal["price"]) < min_notional:
            return 0

        return final_qty