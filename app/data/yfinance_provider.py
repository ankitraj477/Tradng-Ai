import time
import pandas as pd
from .provider import MarketDataProvider
from .cache import MarketDataCache
from .validator import validate_history
from .manifest import DatasetManifest
from ..universe import Universe

class YFinanceProvider(MarketDataProvider):
    """Free public-data provider with bounded retry and cache fallback."""
    def __init__(self, symbols=None, universe_file="data/nifty500.csv", cache=None, retries=2):
        if symbols is None:
            try:
                symbols=[x.symbol for x in Universe(universe_file).load()]
            except Exception:
                symbols=[]
        self._symbols=symbols
        self.cache=cache or MarketDataCache()
        self.manifest=DatasetManifest()
        self.retries=max(0,int(retries))

    def symbols(self): return self._symbols

    def _download(self,symbol,period,interval):
        import yfinance as yf
        last=None
        for attempt in range(self.retries+1):
            try:
                df=yf.download(symbol,period=period,interval=interval,auto_adjust=False,progress=False,threads=False)
                if df is not None and not df.empty:return df
            except Exception as e:
                last=e
            if attempt<self.retries: time.sleep(0.5*(attempt+1))
        if last: raise last
        return None

    def history(self,symbol,period="60d",interval="5m"):
        try:
            df=self._download(symbol,period,interval)
            if df is not None and not df.empty:
                if hasattr(df.columns,"levels"):
                    df.columns=[c[0] if isinstance(c,tuple) else c for c in df.columns]
                df=df[["Open","High","Low","Close","Volume"]].dropna()
                ok,msg=validate_history(df, max_age_seconds=60*60*24*3, require_fresh=False)
                if not ok: raise ValueError(f"provider data rejected: {msg}")
                self.cache.save(symbol,period,interval,df)
                self.manifest.record('yfinance','ohlcv',symbol,df.index.min(),df.index.max(),len(df),adjusted=False)
                return df
        except Exception:
            pass
        cached=self.cache.load(symbol,period,interval)
        if cached is not None:return cached
        raise RuntimeError(f"no live or cached data available for {symbol}")


    def history_many(self,symbols,period="60d",interval="5m"):
        """Best-effort batch download to avoid hundreds of requests per cycle."""
        if not symbols:return {}
        try:
            import yfinance as yf
            df=yf.download(symbols,period=period,interval=interval,auto_adjust=False,progress=False,threads=True,group_by="ticker")
            out={}
            if df is None or df.empty:return out
            for symbol in symbols:
                try:
                    part=df[symbol].dropna() if hasattr(df.columns,"levels") and symbol in df.columns.get_level_values(0) else df.dropna()
                    part=part[["Open","High","Low","Close","Volume"]]
                    ok,_=validate_history(part,max_age_seconds=60*60*24*3,require_fresh=False)
                    if ok:
                        self.cache.save(symbol,period,interval,part); out[symbol]=part
                except Exception:
                    continue
            return out
        except Exception:
            return {}

    def quote(self,symbol):
        df=self.history(symbol,period="5d",interval="5m")
        if df is None or df.empty:return None
        ts=df.index[-1]
        if getattr(ts,"tzinfo",None) is None:ts=ts.tz_localize("UTC")
        return {"symbol":symbol,"price":float(df.Close.iloc[-1]),"timestamp":ts.to_pydatetime()}
