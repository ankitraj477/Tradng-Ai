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

    def symbols(self):
        return [
            row.symbol
            for row in self.rows
            if row.active
        ]

    def validate(self, min_symbols=450):
        count = len(self.symbols())
        return count >= min_symbols, count

    def metadata(self):
        return {
            row.symbol: row
            for row in self.rows
        }