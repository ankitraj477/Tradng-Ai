
def is_long_option_position(p: dict) -> bool:
    """
    Return True when an FNO position is a directional Long Call/Put Option Buy
    (target > entry, side LONG/BUY, not a legacy spread/condor row).
    """
    if str(p.get("product_type", "")).upper() != "FNO":
        return False
    side = str(p.get("side", "SELL")).upper()
    if side not in ("LONG", "BUY"):
        return False
    strat = str(p.get("strategy") or "").lower()
    if "spread" in strat or "condor" in strat:
        return False
    entry = float(p.get("entry_price") or 0.0)
    target = float(p.get("target") or 0.0)
    if target > 0 and entry > 0 and target < entry:
        return False
    return True


def portfolio_metrics(account, positions, short_margin_pct=0.25):
    account = account or {}
    cash = float(account.get("cash", 0) or 0)
    long_value = sum(float(p["qty"]) * float(p["current_price"]) for p in positions if p["side"] == "LONG")
    short_notional = sum(float(p["qty"]) * float(p["current_price"]) for p in positions if p["side"] in ("SHORT", "SELL"))
    short_unrealized = sum((float(p["entry_price"]) - float(p["current_price"])) * float(p["qty"])
                         for p in positions if p["side"] in ("SHORT", "SELL"))
    long_unrealized = sum((float(p["current_price"]) - float(p["entry_price"])) * float(p["qty"])
                        for p in positions if p["side"] == "LONG")
    reserved_margin = sum(float(p["entry_price"]) * float(p["qty"]) * short_margin_pct
                        for p in positions if p["side"] == "SHORT")
    # For FNO spreads/condors, margin was deducted directly from cash on open.
    # For FNO directional LONG option buys, current market value is already included in long_value.
    fno_margin = sum(
        float(p.get("entry_cost") or 2500.0)
        for p in positions
        if str(p.get("product_type", "")).upper() == "FNO"
        and not is_long_option_position(p)
    )
    equity = cash + long_value + short_unrealized + fno_margin
    gross = long_value + short_notional
    net = long_value - short_notional
    return {
        "cash": cash, "equity": equity, "long_value": long_value,
        "short_notional": short_notional, "long_unrealized": long_unrealized,
        "short_unrealized": short_unrealized, "reserved_margin": reserved_margin,
        "gross_exposure": gross, "net_exposure": net,
        "available_cash": max(0.0, cash - reserved_margin)
    }

