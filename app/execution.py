from datetime import datetime, timezone

class PaperExecution:
    def __init__(self,db,cfg): self.db=db; self.cfg=cfg

    def _slip(self,price,side):
        b=self.cfg['execution']['slippage_bps']/10000
        if side=='BUY': return price*(1+b)
        return price*(1-b)

    def buy(self,p,qty,regime):
        if qty<=0 or any(x['symbol']==p['symbol'] for x in self.db.positions()): return False
        a=self.db.account(); fill=self._slip(p['price'],'BUY'); value=fill*qty; cost=self.cost(value,'BUY','INTRADAY')
        if value+cost>a['cash']: return False
        with self.db.conn() as c:
            c.execute("""INSERT INTO positions(symbol,side,qty,entry_price,current_price,stop_loss,target,strategy,confidence,opened_at,sector,atr)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",(p['symbol'],'LONG',qty,fill,fill,p['stop_loss'],p['target'],p['strategy'],p['confidence'],datetime.now(timezone.utc).isoformat(),p.get('sector','Unknown'),p.get('atr')))
            c.execute("UPDATE account SET cash=?,updated_at=? WHERE id=1",(a['cash']-value-cost,datetime.now(timezone.utc).isoformat()))
        self.db.log('INFO',f"PAPER BUY {p['symbol']} x{qty} @ {fill:.2f}"); return True

    def short(self,p,qty,regime):
        if qty<=0 or any(x['symbol']==p['symbol'] for x in self.db.positions()): return False
        a=self.db.account(); fill=self._slip(p['price'],'SELL'); notional=fill*qty
        margin_pct=self.cfg['execution'].get('short_margin_pct',0.25); margin=notional*margin_pct
        entry_cost=self.cost(notional,'SELL','INTRADAY')
        if margin+entry_cost>a['cash']: return False
        with self.db.conn() as c:
            c.execute("""INSERT INTO positions(symbol,side,qty,entry_price,current_price,stop_loss,target,strategy,confidence,opened_at,sector,atr)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",(p['symbol'],'SHORT',qty,fill,fill,p['stop_loss'],p['target'],p['strategy'],p['confidence'],datetime.now(timezone.utc).isoformat(),p.get('sector','Unknown'),p.get('atr')))
            # Margin is reserved against the account but is tracked separately in the position.
            # Only actual entry costs leave cash; this keeps cash/equity accounting consistent.
            c.execute("UPDATE account SET cash=?,updated_at=? WHERE id=1",(a['cash']-entry_cost,datetime.now(timezone.utc).isoformat()))
        self.db.log('INFO',f"PAPER SHORT {p['symbol']} x{qty} @ {fill:.2f} margin={margin:.2f}"); return True

    def mark(self,quotes):
        with self.db.conn() as c:
            for q in quotes: c.execute("UPDATE positions SET current_price=? WHERE symbol=?",(q['price'],q['symbol']))

    def close(self,symbol,price,reason,regime):
        with self.db.conn() as c:
            row=c.execute("SELECT * FROM positions WHERE symbol=?",(symbol,)).fetchone()
            if not row:return False
            p=dict(row); side=p['side']; fill=self._slip(price,'SELL' if side=='LONG' else 'BUY'); notional=abs(fill*p['qty'])
            if side=='LONG':
                gross=(fill-p['entry_price'])*p['qty']; released=fill*p['qty']; entry_cap=p['entry_price']*p['qty']
            else:
                gross=(p['entry_price']-fill)*p['qty']; released=gross; entry_cap=p['entry_price']*p['qty']
            exit_cost=self.cost(notional,'SELL' if side=='LONG' else 'BUY','INTRADAY')
            pnl=gross-exit_cost
            cash=self.db.account()['cash']+released-exit_cost
            opened=datetime.fromisoformat(p['opened_at']); holding=(datetime.now(timezone.utc)-opened).total_seconds()
            pnl_pct=pnl/entry_cap*100 if entry_cap else 0
            c.execute("""INSERT INTO trades(symbol,action,side,entry_price,exit_price,qty,capital,stop_loss,target,holding_seconds,pnl,pnl_pct,strategy,confidence,regime,entry_reason,exit_reason,risk_decision,created_at)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(symbol,'SELL' if side=='LONG' else 'COVER',side,p['entry_price'],fill,p['qty'],entry_cap,p['stop_loss'],p['target'],holding,pnl,pnl_pct,p['strategy'],p['confidence'],regime,'AI proposal',reason,'APPROVED',datetime.now(timezone.utc).isoformat()))
            c.execute("DELETE FROM positions WHERE symbol=?",(symbol,)); c.execute("UPDATE account SET cash=?,updated_at=? WHERE id=1",(cash,datetime.now(timezone.utc).isoformat()))
        self.db.log('INFO',f"PAPER {side} CLOSE {symbol} @ {fill:.2f} P&L={pnl:.2f}"); return True

    def cost(self,value,action,segment='INTRADAY'):
        e=self.cfg['execution']; brokerage=value*e.get('brokerage_pct',e.get('brokerage',0))/100
        sebi=value*e.get('sebi_turnover_fee_pct',0)/100
        gst=(brokerage+sebi)*e.get('gst_pct',0.18)
        stamp_pct=e.get('stamp_duty_non_delivery_pct',0.003) if segment=='INTRADAY' else e.get('stamp_duty_delivery_pct',0.015)
        stamp=value*stamp_pct/100 if action=='BUY' else 0
        stt_pct=e.get('stt_intraday_sell_pct',0.025) if segment=='INTRADAY' else e.get('stt_delivery_pct',0.10)
        stt=value*stt_pct/100 if action=='SELL' else 0
        return brokerage+sebi+gst+stamp+stt
