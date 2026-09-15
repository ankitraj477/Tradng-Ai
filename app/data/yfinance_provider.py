import pandas as pd
from .provider import MarketDataProvider
from .cache import MarketDataCache
from .validator import validate_history
from .manifest import DatasetManifest
from ..universe import Universe

class YFinanceProvider(MarketDataProvider):
    def __init__(self, symbols=None, universe_file="data/nifty500.csv", cache=None):
        if symbols is None:
            try:
                symbols=Universe(universe_file).load()
                symbols=[x.symbol for x in symbols]
            except Exception:
                symbols=[]
        self._symbols=symbols
        self.cache=cache or MarketDataCache()
        self.manifest=DatasetManifest()

    def symbols(self):
        return self._symbols

    def history(self,symbol,period="3mo",interval="5m"):
        try:
            import yfinance as yf
        except ImportError:
            return self.cache.load(symbol,period,interval)
        if yf is None:
            cached=self.cache.load(symbol,period,interval)
            if cached is not None: return cached
            raise RuntimeError("yfinance is not installed; install requirements.txt for live data")
        df=yf.download(symbol,period=period,interval=interval,auto_adjust=False,progress=False,threads=False)
        if df is None or df.empty:
            return self.cache.load(symbol,period,interval)
        if hasattr(df.columns,"levels"):
            df.columns=[c[0] if isinstance(c,tuple) else c for c in df.columns]
        df=df[["Open","High","Low","Close","Volume"]].dropna()
        self.cache.save(symbol,period,interval,df)
        self.manifest.record('yfinance', 'ohlcv', symbol, df.index.min(), df.index.max(), len(df), adjusted=False)
        return df

    def quote(self,symbol):
        df=self.history(symbol,period="5d",interval="5m")
        if df is None or df.empty:return None
        ts=df.index[-1]
        if getattr(ts,"tzinfo",None) is None:ts=ts.tz_localize("UTC")
        return {"symbol":symbol,"price":float(df.Close.iloc[-1]),"timestamp":ts.to_pydatetime()}
