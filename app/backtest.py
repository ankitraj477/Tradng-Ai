import pandas as pd, numpy as np
from .indicators import indicators

class Backtester:
    """Single-symbol long backtest. Signal at close t, fill at open t+1."""
    def __init__(self,starting_cash=1000,fee_bps=10,slippage_bps=8):
        self.starting_cash=starting_cash; self.cash=starting_cash; self.fee_bps=fee_bps; self.slippage_bps=slippage_bps; self.trades=[]; self.equity=[]

    def run(self,df,symbol='TEST'):
        if df.empty:return self.result()
        x=indicators(df).dropna().reset_index(drop=False); position=None; pending=False
        for i in range(len(x)):
            row=x.iloc[i]; o=float(row['Open']); h=float(row['High']); l=float(row['Low']); close=float(row['Close'])
            if pending and position is None:
                fill=o*(1+self.slippage_bps/10000); risk=max(float(row['atr'])*1.5,fill*0.005)
                qty=min(int(self.cash*0.02/risk),int(self.cash/(fill*(1+self.fee_bps/10000))))
                if qty>0:
                    value=fill*qty; fee=value*self.fee_bps/10000; self.cash-=value+fee; position={'entry':fill,'qty':qty,'stop':fill-risk,'target':fill+3*risk,'entry_i':i}
                pending=False
            if position:
                if l<=position['stop']:
                    self._exit(symbol,position,position['stop'],'stop')
                    position=None
                elif h>=position['target']:
                    self._exit(symbol,position,position['target'],'target')
                    position=None
            bullish=(close>row['ema20']>row['ema50'] and row['rsi']>55 and row['rel_volume']>1.2)
            if position is None and not pending and bullish and i+1<len(x):pending=True
            mark=self.cash+(position['qty']*close if position else 0); self.equity.append(mark)
        if position:self._exit(symbol,position,float(x.iloc[-1]['Close']),'end')
        return self.result()

    def run_portfolio(self,datasets,max_positions=5,max_position_pct=0.20):
        """Synchronized multi-symbol long portfolio using next-bar-open execution."""
        prepared={s:indicators(df).dropna() for s,df in datasets.items() if df is not None and not df.empty}
        idx=sorted(set().union(*(set(df.index) for df in prepared.values()))) if prepared else []
        positions={}; pending={}; self.cash=self.starting_cash; self.trades=[]; self.equity=[]
        for ts in idx:
            for s,df in prepared.items():
                if ts not in df.index: continue
                row=df.loc[ts]; o=float(row['Open']); h=float(row['High']); l=float(row['Low']); close=float(row['Close'])
                if s in pending and s not in positions:
                    fill=o*(1+self.slippage_bps/10000); risk=max(float(row['atr'])*1.5,fill*0.005); max_value=self.starting_cash*max_position_pct
                    qty=min(int(self.cash*0.02/risk),int(max_value/fill),int(self.cash/(fill*(1+self.fee_bps/10000))))
                    if qty>0:
                        value=fill*qty; self.cash-=value+value*self.fee_bps/10000; positions[s]={'entry':fill,'qty':qty,'stop':fill-risk,'target':fill+3*risk}
                    pending.pop(s,None)
                if s in positions:
                    p=positions[s]
                    if l<=p['stop']:self._exit(s,p,p['stop'],'stop');positions.pop(s)
                    elif h>=p['target']:self._exit(s,p,p['target'],'target');positions.pop(s)
                bullish=(close>row['ema20']>row['ema50'] and row['rsi']>55 and row['rel_volume']>1.2)
                if s not in positions and len(positions)<max_positions and bullish:pending[s]=True
            value=self.cash+sum(p['qty']*prepared[s].loc[ts,'Close'] for s,p in positions.items() if ts in prepared[s].index); self.equity.append(value)
        for s,p in list(positions.items()):self._exit(s,p,float(prepared[s].iloc[-1]['Close']),'end')
        return self.result()

    def _exit(self,symbol,p,price,reason):
        fill=price*(1-self.slippage_bps/10000); gross=(fill-p['entry'])*p['qty']; fee=fill*p['qty']*self.fee_bps/10000; pnl=gross-fee; self.cash+=fill*p['qty']-fee
        self.trades.append({'symbol':symbol,'entry':p['entry'],'exit':fill,'qty':p['qty'],'pnl':pnl,'reason':reason})

    def result(self):
        curve=np.array(self.equity or [self.starting_cash],dtype=float); peak=np.maximum.accumulate(curve); dd=(peak-curve)/peak; pnls=[t['pnl'] for t in self.trades]; wins=[x for x in pnls if x>0]; losses=[x for x in pnls if x<0]
        return {'start':self.starting_cash,'end':float(self.cash),'pnl':float(self.cash-self.starting_cash),'return_pct':float((self.cash/self.starting_cash-1)*100),'trades':len(pnls),'win_rate':len(wins)/len(pnls)*100 if pnls else 0,'profit_factor':sum(wins)/abs(sum(losses)) if losses else None,'max_drawdown_pct':float(dd.max()*100) if len(dd) else 0,'trades_detail':self.trades}
