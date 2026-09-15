import numpy as np

def buy_hold(df, starting_cash=1000):
    if df is None or df.empty:return {}
    first=float(df["Close"].iloc[0]); last=float(df["Close"].iloc[-1])
    qty=int(starting_cash/first)
    cash=starting_cash-qty*first
    end=cash+qty*last
    return {"start":starting_cash,"end":end,"return_pct":(end/starting_cash-1)*100,"qty":qty}

def metrics(pnls, equity):
    pnls=np.asarray(pnls,dtype=float); eq=np.asarray(equity,dtype=float)
    daily= np.diff(eq)/eq[:-1] if len(eq)>1 else np.array([])
    sharpe=(daily.mean()/daily.std()*np.sqrt(252)) if len(daily)>1 and daily.std()>0 else None
    downside=daily[daily<0]
    sortino=(daily.mean()/downside.std()*np.sqrt(252)) if len(downside)>1 and downside.std()>0 else None
    return {"sharpe":sharpe,"sortino":sortino}
