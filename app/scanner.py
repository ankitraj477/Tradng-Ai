import subprocess, json, os
from .indicators import indicators

class Scanner:
    def __init__(self, max_candidates=50, use_cpp=False):
        self.max_candidates=max_candidates
        self.use_cpp=use_cpp

    def scan(self, provider, cash):
        rows=[]
        metadata = provider.metadata() if hasattr(provider, "metadata") else {}
        for symbol in provider.symbols():
            try:
                q=provider.quote(symbol)
                if not q or q["price"] <= 0: continue
                if q["price"] > cash: continue
                df=provider.history(symbol)
                if len(df)<60: continue
                x=indicators(df)
                if x.empty: continue
                z=x.iloc[-1]
                score=0
                if z["Close"]>z["ema20"]>z["ema50"]: score+=30
                if z["rsi"]>55: score+=15
                if z["rel_volume"]>1.2: score+=20
                if z["ret_5"]>0: score+=15
                if z["ret_20"]>0: score+=10
                if z["Close"]>z["vwap"]: score+=10
                rows.append({
                    "symbol":symbol,"price":float(z["Close"]),"score":float(score),
                    "rsi":float(z["rsi"]),"atr":float(z["atr"]),
                    "rel_volume":float(z["rel_volume"]),"ret_5":float(z["ret_5"]),
                    "ret_20":float(z["ret_20"]),"volatility":float(z["volatility"]),"sector":getattr(metadata.get(symbol), "sector", "Unknown")
                })
            except Exception:
                continue
        return sorted(rows,key=lambda r:r["score"],reverse=True)[:self.max_candidates]
