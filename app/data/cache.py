from pathlib import Path
import json, time
import pandas as pd

class MarketDataCache:
    """Simple disk cache. Keeps the first implementation lightweight and restart-safe."""
    def __init__(self, root="data/cache"):
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)

    def key(self,symbol,period,interval):
        return symbol.replace("/","_").replace(".","_")+f"_{period}_{interval}"

    def path(self,symbol,period,interval):
        return self.root/(self.key(symbol,period,interval)+".csv")

    def save(self,symbol,period,interval,df):
        p=self.path(symbol,period,interval)
        df.to_csv(p)
        return p

    def load(self,symbol,period,interval,max_age_seconds=None):
        p=self.path(symbol,period,interval)
        if not p.exists(): return None
        if max_age_seconds is not None and time.time()-p.stat().st_mtime>max_age_seconds:
            return None
        try:
            df=pd.read_csv(p,index_col=0,parse_dates=True)
            return df
        except Exception:
            return None
