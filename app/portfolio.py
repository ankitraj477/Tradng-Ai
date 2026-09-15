class PortfolioManager:
    def __init__(self, db, cfg): self.db=db; self.cfg=cfg

    def state(self):
        a=self.db.account(); positions=self.db.positions()
        long_value=sum(p['qty']*p['current_price'] for p in positions if p['side']=='LONG')
        short_notional=sum(p['qty']*p['current_price'] for p in positions if p['side']=='SHORT')
        short_unrealized=sum((p['entry_price']-p['current_price'])*p['qty'] for p in positions if p['side']=='SHORT')
        equity=a['cash']+long_value+short_unrealized
        return a,positions,long_value,short_notional,equity

    def size(self, proposal):
        a,positions,long_value,short_notional,equity=self.state()
        if equity <= 0: return 0
        risk_cash=equity*self.cfg['risk']['max_position_risk_pct']
        per_share=max(abs(proposal['price']-proposal['stop_loss']),0.01)
        qty_by_risk=int(risk_cash/per_share)
        max_exposure=equity*self.cfg['risk']['max_portfolio_invested_pct']
        current_exposure=long_value+short_notional
        remaining=max(0,max_exposure-current_exposure)
        qty_by_portfolio=int(remaining/proposal['price'])
        side=proposal.get('action')
        if side=='BUY':
            qty_by_cash=int(max(0,a['cash'])/proposal['price'])
        elif side=='SHORT':
            margin_pct=self.cfg['execution'].get('short_margin_pct',0.25)
            qty_by_cash=int(max(0,a['cash'])/(proposal['price']*margin_pct))
        else: return 0
        return max(0,min(qty_by_risk,qty_by_portfolio,qty_by_cash))
