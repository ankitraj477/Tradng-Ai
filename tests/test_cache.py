import pandas as pd
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.data.cache import MarketDataCache

def test_cache_roundtrip(tmp_path):
    c=MarketDataCache(tmp_path)
    df=pd.DataFrame({"Open":[1],"High":[2],"Low":[1],"Close":[1.5],"Volume":[10]})
    c.save("ABC.NS","1mo","1d",df)
    got=c.load("ABC.NS","1mo","1d")
    assert got is not None
    assert float(got.Close.iloc[0])==1.5
