class RiskManager:
    def __init__(self,db,cfg): self.db=db; self.cfg=cfg

    def equity(self):
        a=self.db.account(); ps=self.db.positions()
        return a['cash']+sum(p['qty']*p['current_price'] for p in ps if p['side']=='LONG')+sum((p['entry_price']-p['current_price'])*p['qty'] for p in ps if p['side']=='SHORT')

    def approve(self,p,qty):
        if qty<=0 or p.get('confidence',0)<60:return 'REJECT'
        if p.get('risk_reward',0)<self.cfg['risk']['min_risk_reward']:return 'REJECT'
        if p.get('action') not in {'BUY','SHORT'}:return 'REJECT'
        if p['action']=='SHORT' and not self.cfg.get('allow_shorts',True):return 'REJECT'
        positions=self.db.positions()
        if any(x['symbol']==p['symbol'] for x in positions):return 'REJECT'
        equity=self.equity()
        if equity<=0:return 'REJECT'
        a=self.db.account()
        margin_pct=self.cfg['execution'].get('short_margin_pct',0.25)
        required=p['price']*qty*(1 if p['action']=='BUY' else margin_pct)
        if required>a['cash']:return 'REJECT'
        if a['peak_value']>0 and (a['peak_value']-equity)/a['peak_value']>=self.cfg['risk']['emergency_drawdown_pct']:return 'REJECT'
        max_exposure=equity*self.cfg['risk']['max_portfolio_invested_pct']
        current=sum(x['qty']*x['current_price'] for x in positions)
        if current+p['price']*qty>max_exposure:return 'REJECT'
        sector=p.get('sector','Unknown')
        sector_exp=sum(x['qty']*x['current_price'] for x in positions if x.get('sector','Unknown')==sector)+p['price']*qty
        if sector_exp/equity>self.cfg['risk']['max_sector_exposure_pct']:return 'REJECT'
        return 'APPROVE'
