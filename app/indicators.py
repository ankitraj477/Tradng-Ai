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
    x["rsi"]=100-(100/(1+rs))
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    x["atr"]=tr.rolling(14).mean()
    x["vwap"]=(x["Close"]*x["Volume"]).cumsum()/x["Volume"].cumsum().replace(0,np.nan)
    x["rel_volume"]=v/v.rolling(20).mean()
    x["ret_5"]=c.pct_change(5)
    x["ret_20"]=c.pct_change(20)
    mid=c.rolling(20).mean(); std=c.rolling(20).std()
    x["bb_upper"]=mid+2*std; x["bb_lower"]=mid-2*std
    x["volatility"]=c.pct_change().rolling(20).std()*np.sqrt(252)
    return x.dropna()
