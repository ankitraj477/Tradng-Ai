import numpy as np
import pandas as pd

def indicators(df):
    x=df.copy()
    c=x["Close"]; h=x["High"]; l=x["Low"]; v=x["Volume"]
    x["ema20"]=c.ewm(span=20,adjust=False).mean()
    x["ema50"]=c.ewm(span=50,adjust=False).mean()
    d=c.diff()
    gain=d.clip(lower=0).rolling(14).mean()
    loss=(-d.clip(upper=0)).rolling(14).mean()
    rs=gain/(loss.replace(0,np.nan))
    rsi=100-(100/(1+rs))
    x["rsi"]=np.where(gain.isna()|loss.isna(),np.nan,np.where(loss==0,np.where(gain>0,100.0,50.0),rsi))
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    x["atr"]=tr.rolling(14).mean()
    vp = x["Close"] * x["Volume"]
    cum_vol = x["Volume"].groupby(x.index.date).cumsum() if hasattr(x.index, "date") else x["Volume"].cumsum()
    cum_vp = vp.groupby(x.index.date).cumsum() if hasattr(x.index, "date") else vp.cumsum()
    x["vwap"] = (cum_vp / cum_vol.replace(0, np.nan)).fillna(c)
    vol_mean = v.rolling(20).mean()
    x["rel_volume"] = (v / vol_mean.replace(0, np.nan)).fillna(1.0)
    x["ret_5"]=c.pct_change(5)
    x["ret_20"]=c.pct_change(20)
    x["ret_day"]=c.pct_change(75).fillna(c.pct_change(20))
    mid=c.rolling(20).mean(); std=c.rolling(20).std()
    x["bb_upper"]=mid+2*std; x["bb_lower"]=mid-2*std
    x["volatility"]=c.pct_change().rolling(20).std()*np.sqrt(252*75)
    out=x.dropna()
    if not out.empty and not df.empty:
        assert out.index[-1]==df.index[-1], "indicators dropped tail rows"
    return out
