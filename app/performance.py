def summarize(trades):
    pnls=[float(t.get("pnl") or 0) for t in trades]
    wins=[p for p in pnls if p>0]; losses=[p for p in pnls if p<0]
    return {
        "total_trades":len(pnls),
        "winning_trades":len(wins),
        "losing_trades":len(losses),
        "win_rate":len(wins)/len(pnls)*100 if pnls else 0,
        "avg_profit":sum(wins)/len(wins) if wins else 0,
        "avg_loss":sum(losses)/len(losses) if losses else 0,
        "profit_factor":sum(wins)/abs(sum(losses)) if losses else None,
        "expectancy":sum(pnls)/len(pnls) if pnls else 0
    }
