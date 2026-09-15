
def portfolio_metrics(account, positions, short_margin_pct=0.25):
    cash=float(account.get("cash",0) or 0)
    long_value=sum(float(p["qty"])*float(p["current_price"]) for p in positions if p["side"]=="LONG")
    short_notional=sum(float(p["qty"])*float(p["current_price"]) for p in positions if p["side"]=="SHORT")
    short_unrealized=sum((float(p["entry_price"])-float(p["current_price"]))*float(p["qty"])
                         for p in positions if p["side"]=="SHORT")
    long_unrealized=sum((float(p["current_price"])-float(p["entry_price"]))*float(p["qty"])
                        for p in positions if p["side"]=="LONG")
    reserved_margin=sum(float(p["entry_price"])*float(p["qty"])*short_margin_pct
                        for p in positions if p["side"]=="SHORT")
    # Cash is the account cash balance; reserved short margin is tracked
    # separately and therefore remains inside cash but outside available cash.
    equity=cash+long_value+short_unrealized
    gross=long_value+short_notional
    net=long_value-short_notional
    return {
        "cash":cash,"equity":equity,"long_value":long_value,
        "short_notional":short_notional,"long_unrealized":long_unrealized,
        "short_unrealized":short_unrealized,"reserved_margin":reserved_margin,
        "gross_exposure":gross,"net_exposure":net,
        "available_cash":max(0,cash-reserved_margin)
    }
