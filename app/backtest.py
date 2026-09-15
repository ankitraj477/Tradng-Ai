import pandas as pd
import numpy as np
from .indicators import indicators

class Backtester:
    """Portfolio backtester. Signals use bar-close data; orders fill next bar open."""
    def __init__(self, starting_cash=1000, fee_bps=10, slippage_bps=8,
                 risk_pct=0.02, max_position_pct=0.20, max_positions=5,
                 short_margin_pct=0.25, max_portfolio_exposure_pct=0.85):
        self.starting_cash=float(starting_cash); self.fee_bps=float(fee_bps)
        self.slippage_bps=float(slippage_bps); self.risk_pct=float(risk_pct)
        self.max_position_pct=float(max_position_pct); self.max_positions=int(max_positions)
        self.short_margin_pct=float(short_margin_pct); self.max_portfolio_exposure_pct=float(max_portfolio_exposure_pct)
        self.cash=self.starting_cash; self.reserved_margin=0.0; self.trades=[]; self.equity=[]

    def _reset(self):
        self.cash=self.starting_cash; self.reserved_margin=0.0; self.trades=[]; self.equity=[]

    def _fee(self,value): return value*self.fee_bps/10000
    def _fill(self,price,side):
        slip=self.slippage_bps/10000
        return price*(1+slip) if side=='BUY' else price*(1-slip)

    def _mark(self,positions, prices):
        value=self.cash
        for s,p in positions.items():
            px=prices.get(s, p.get('mark', p['entry']))
            if p['side']=='LONG': value += p['qty']*px
            else: value += (p['entry']-px)*p['qty']
        return value

    def _open(self,s,row,side,equity):
        price=float(row['Open']); fill=self._fill(price,'BUY' if side=='LONG' else 'SELL')
        risk=max(float(row['atr'])*1.5,fill*.005)
        qty_by_risk=int(equity*self.risk_pct/risk)
        qty_by_position=int((equity*self.max_position_pct)/fill)
        current_exposure=sum(x['qty']*x['entry'] for x in getattr(self,'_positions_for_sizing',{}).values())
        remaining_exposure=max(0,equity*self.max_portfolio_exposure_pct-current_exposure)
        qty_by_total=int(remaining_exposure/fill)
        if side=='LONG':
            qty_by_cash=int(self.cash/(fill+self._fee(fill)))
        else:
            margin=fill*self.short_margin_pct
            available=max(0,self.cash-self.reserved_margin)
            qty_by_cash=int(available/(margin+self._fee(fill)))
        qty=max(0,min(qty_by_risk,qty_by_position,qty_by_total,qty_by_cash))
        if qty<=0:return None
        notional=fill*qty; fee=self._fee(notional)
        if side=='LONG':
            self.cash-=notional+fee; stop=fill-risk; target=fill+3*risk; margin=0
        else:
            margin=notional*self.short_margin_pct; self.reserved_margin+=margin; self.cash-=fee
            stop=fill+risk; target=fill-3*risk
        return {'side':side,'entry':fill,'qty':qty,'stop':stop,'target':target,'margin':margin,'entry_i':row.name}

    def _close(self,s,p,price,reason):
        side=p['side']; fill=self._fill(float(price),'SELL' if side=='LONG' else 'BUY')
        notional=fill*p['qty']; fee=self._fee(notional)
        if side=='LONG':
            pnl=(fill-p['entry'])*p['qty']-fee; self.cash+=notional-fee
        else:
            gross=(p['entry']-fill)*p['qty']; pnl=gross-fee; self.reserved_margin-=p['margin']; self.cash+=gross-fee
        self.trades.append({'symbol':s,'side':side,'entry':p['entry'],'exit':fill,'qty':p['qty'],'pnl':pnl,'reason':reason})

    def _run(self,prepared):
        positions={}; pending={}
        self._positions_for_sizing=positions
        idx=sorted(set().union(*(set(df.index) for df in prepared.values()))) if prepared else []
        for ts in idx:
            # Fill orders created on the previous close.
            prices={}
            for s,df in prepared.items():
                if ts not in df.index: continue
                row=df.loc[ts]; prices[s]=float(row['Close'])
                if s in pending and s not in positions and len(positions)<self.max_positions:
                    p=self._open(s,row,pending.pop(s),self._mark(positions,prices));
                    if p:
                        p['mark']=prices[s]
                        positions[s]=p
            # Stops/targets are checked only after the position exists at this bar's open.
            for s in list(positions):
                if ts not in prepared[s].index: continue
                row=prepared[s].loc[ts]; p=positions[s]
                hit_stop=(float(row['Low'])<=p['stop']) if p['side']=='LONG' else (float(row['High'])>=p['stop'])
                hit_target=(float(row['High'])>=p['target']) if p['side']=='LONG' else (float(row['Low'])<=p['target'])
                p['mark']=float(row['Close'])
                if hit_stop:
                    self._close(s,p,p['stop'],'stop'); positions.pop(s)
                elif hit_target:
                    self._close(s,p,p['target'],'target'); positions.pop(s)
            # Generate signals only from the just-closed bar for next bar.
            for s,df in prepared.items():
                if ts not in df.index or s in positions or s in pending: continue
                i=df.index.get_loc(ts)
                if i+1>=len(df): continue
                row=df.iloc[i]
                bullish=row['Close']>row['ema20']>row['ema50'] and row['rsi']>55 and row['rel_volume']>1.2
                bearish=row['Close']<row['ema20']<row['ema50'] and row['rsi']<45 and row['rel_volume']>1.2
                if bullish: pending[s]='LONG'
                elif bearish: pending[s]='SHORT'
            if prices:self.equity.append(self._mark(positions,prices))
        for s,p in list(positions.items()):
            self._close(s,p,float(prepared[s].iloc[-1]['Close']),'end')
        self._positions_for_sizing={}
        return self.result()

    def run(self,df,symbol='TEST'):
        self._reset()
        if df is None or df.empty:return self.result()
        return self._run({symbol:indicators(df).dropna()})

    def run_portfolio(self,datasets,max_positions=None,max_position_pct=None):
        self._reset()
        if max_positions is not None:self.max_positions=int(max_positions)
        if max_position_pct is not None:self.max_position_pct=float(max_position_pct)
        prepared={s:indicators(df).dropna() for s,df in datasets.items() if df is not None and not df.empty}
        return self._run(prepared)

    def result(self):
        curve=np.array(self.equity or [self.starting_cash],dtype=float)
        peak=np.maximum.accumulate(curve); dd=(peak-curve)/peak
        pnls=[t['pnl'] for t in self.trades]; wins=[x for x in pnls if x>0]; losses=[x for x in pnls if x<0]
        return {'start':self.starting_cash,'end':float(self.cash),'pnl':float(self.cash-self.starting_cash),
                'return_pct':float((self.cash/self.starting_cash-1)*100),'trades':len(pnls),
                'win_rate':len(wins)/len(pnls)*100 if pnls else 0,
                'profit_factor':sum(wins)/abs(sum(losses)) if losses else None,
                'max_drawdown_pct':float(dd.max()*100) if len(dd) else 0,
                'trades_detail':self.trades}
