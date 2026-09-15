from dataclasses import dataclass
from pathlib import Path
import pandas as pd

@dataclass
class SymbolMeta:
    symbol: str
    company: str = ""
    sector: str = "Unknown"
    industry: str = "Unknown"
    active: bool = True

class Universe:
    def __init__(self, path="data/nifty500.csv"):
        self.path=Path(path)
        self.rows=[]

    def load(self):
        if not self.path.exists():
            raise FileNotFoundError(f"Universe file missing: {self.path}")
        df=pd.read_csv(self.path)
        if "symbol" not in df.columns:
            raise ValueError("Universe file must contain a symbol column")
        df=df.dropna(subset=["symbol"]).copy()
        df["symbol"]=df["symbol"].astype(str).str.strip()
        df=df[df["symbol"]!=""].drop_duplicates("symbol")
        for col in ["company","sector","industry"]:
            if col not in df: df[col]="Unknown" if col!="company" else ""
        self.rows=[SymbolMeta(r.symbol,r.company,r.sector,r.industry) for r in df.itertuples()]
        return self.rows

    def symbols(self):
        return [x.symbol for x in self.rows if x.active]

    def metadata(self):
        return {x.symbol:x for x in self.rows}
