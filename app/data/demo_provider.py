import numpy as np, pandas as pd
from datetime import datetime, timedelta, timezone
from .provider import MarketDataProvider

class DemoProvider(MarketDataProvider):
    """Deterministic synthetic market. History is generated once per symbol and reused."""
    def __init__(self, symbols=None):
        self._symbols=symbols or ["^NSEI","RELIANCE.NS","TCS.NS","INFY.NS","SBIN.NS","ITC.NS","WIPRO.NS"]
        self.rng=np.random.default_rng(42)
        self._data={s:self._make(s) for s in self._symbols}

    def symbols(self): return self._symbols

    def _make(self,symbol):
        n=1000
        base=100+self._symbols.index(symbol)*70
        returns=self.rng.normal(0.0002,0.008,n)
        close=base*np.exp(np.cumsum(returns))
        idx=pd.date_range(datetime.now(timezone.utc)-timedelta(minutes=5*n),periods=n,freq="5min")
        df=pd.DataFrame({"Close":close},index=idx)
        df["Open"]=df["Close"].shift(1).fillna(df["Close"])
        df["High"]=df[["Open","Close"]].max(axis=1)*1.002
        df["Low"]=df[["Open","Close"]].min(axis=1)*0.998
        df["Volume"]=self.rng.integers(10000,100000,n)
        return df

    def history(self,symbol,period="3mo",interval="5m"):
        return self._data[symbol].copy()

    def quote(self,symbol):
        df=self._data[symbol]
        return {"symbol":symbol,"price":float(df.Close.iloc[-1]),"timestamp":df.index[-1].to_pydatetime()}
