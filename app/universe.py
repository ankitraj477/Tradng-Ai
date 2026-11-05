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
        self.path = Path(path)
        self.rows = []

    @staticmethod
    def _as_bool(value):
        if pd.isna(value):
            return True

        if isinstance(value, bool):
            return value

        if isinstance(value, (int, float)):
            return bool(value)

        return str(value).strip().lower() not in {
            "0",
            "false",
            "no",
            "n",
            "inactive",
        }

    def load(self):
        if not self.path.exists():
            raise FileNotFoundError(
                f"Universe file missing: {self.path}"
            )

        df = pd.read_csv(self.path)

        if "symbol" not in df.columns:
            raise ValueError(
                "Universe file must contain a symbol column"
            )

        df = df.dropna(
            subset=["symbol"]
        ).copy()

        df["symbol"] = (
            df["symbol"]
            .astype(str)
            .str.strip()
        )

        df = (
            df[df["symbol"] != ""]
            .drop_duplicates("symbol")
        )

        if "company" not in df:
            df["company"] = ""

        for column in ("sector", "industry"):
            if column not in df:
                df[column] = "Unknown"

        if "active" not in df:
            df["active"] = True

        self.rows = [
            SymbolMeta(
                str(row.symbol),
                str(row.company),
                str(row.sector),
                str(row.industry),
                self._as_bool(row.active),
            )
            for row in df.itertuples(index=False)
        ]

        return self.rows

    def symbols(self, priority_first=True):
        raw_syms = [
            row.symbol
            for row in self.rows
            if row.active
        ]
        if not priority_first:
            return raw_syms

        # Return institutional priority liquid leaders first, followed by remainder
        raw_set = set(raw_syms)
        priority = [s for s in PRIORITY_LIQUID_SYMBOLS if s in raw_set]
        priority_set = set(priority)
        remainder = [s for s in raw_syms if s not in priority_set]
        return priority + remainder

    def validate(self, min_symbols=450):
        count = len(self.symbols())
        return count >= min_symbols, count

    def metadata(self):
        return {
            row.symbol: row
            for row in self.rows
        }


PRIORITY_LIQUID_SYMBOLS = [
    # Top Nifty 50 index constituents & market leaders
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "BHARTIARTL.NS", "SBIN.NS", "ITC.NS", "HINDUNILVR.NS", "LT.NS",
    "BAJFINANCE.NS", "HCLTECH.NS", "MARUTI.NS", "SUNPHARMA.NS", "ADANIENT.NS",
    "KOTAKBANK.NS", "TITAN.NS", "ONGC.NS", "NTPC.NS", "AXISBANK.NS",
    "POWERGRID.NS", "M&M.NS", "COALINDIA.NS", "BAJAJFINSV.NS", "ULTRACEMCO.NS",
    "WIPRO.NS", "JSWSTEEL.NS", "GRASIM.NS", "TATASTEEL.NS", "TECHM.NS",
    "HINDALCO.NS", "NESTLEIND.NS", "ADANIPORTS.NS", "DRREDDY.NS", "CIPLA.NS",
    "BPCL.NS", "SBILIFE.NS", "BRITANNIA.NS", "EICHERMOT.NS", "HDFCLIFE.NS",
    "DIVISLAB.NS", "HEROMOTOCO.NS", "APOLLOHOSP.NS", "SHRIRAMFIN.NS", "TATACONSUM.NS",
    "BAJAJ-AUTO.NS", "BEL.NS", "TRENT.NS", "ASIANPAINT.NS",
    # Active high-momentum & liquidity leaders
    "ANGELONE.NS", "360ONE.NS", "APLAPOLLO.NS", "ABDL.NS", "ANANDRATHI.NS",
]


DEFAULT_BENCHMARK_SYMBOLS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS", "LT.NS", "ITC.NS",
    "AXISBANK.NS", "HINDUNILVR.NS", "BAJFINANCE.NS", "MARUTI.NS", "ASIANPAINT.NS"
]


def get_universe_symbols(path=None):
    try:
        u = Universe(path or (Path(__file__).resolve().parent.parent / "data" / "nifty500.csv"))
        u.load()
        syms = u.symbols()
        if syms:
            return syms
    except Exception:
        pass
    return list(DEFAULT_BENCHMARK_SYMBOLS)