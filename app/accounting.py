
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
    # For FNO positions, margin was deducted directly from cash on open.
    # We track that locked capital to ensure equity accurately reflects account value.
    fno_margin = sum(float(p.get("entry_cost") or 2500.0)
                     for p in positions if str(p.get("product_type", "")).upper() == "FNO")
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

