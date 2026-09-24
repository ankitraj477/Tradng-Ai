"""
Convert the official NSE NIFTY 500 constituent CSV into the
normalized universe format used by the paper trader.

Usage:
    python scripts/update_universe.py data/ind_nifty500list.csv
"""

import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "nifty500.csv"


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python scripts/update_universe.py <nse_nifty500.csv>"
        )

    source = Path(sys.argv[1])

    if not source.exists():
        raise SystemExit(f"Input file not found: {source}")

    df = pd.read_csv(source)

    required = {
        "Company Name",
        "Industry",
        "Symbol",
        "Series",
        "ISIN Code",
    }

    missing = required - set(df.columns)

    if missing:
        raise SystemExit(
            f"Official NSE CSV is missing columns: {sorted(missing)}"
        )

    # Keep equity-listed constituents only.
    df = df[
        df["Series"]
        .astype(str)
        .str.strip()
        .eq("EQ")
    ].copy()

    df["Symbol"] = (
        df["Symbol"]
        .astype(str)
        .str.strip()
    )

    df["Company Name"] = (
        df["Company Name"]
        .astype(str)
        .str.strip()
    )

    df["Industry"] = (
        df["Industry"]
        .astype(str)
        .str.strip()
    )

    # Remove empty/duplicate symbols.
    df = (
        df[df["Symbol"] != ""]
        .drop_duplicates("Symbol")
        .reset_index(drop=True)
    )

    # Yahoo Finance uses the .NS suffix for NSE-listed equities.
    df["symbol"] = df["Symbol"] + ".NS"

    df["company"] = df["Company Name"]

    # NSE's downloadable constituent file provides Industry,
    # not our separate sector taxonomy. For now we use Industry
    # for both fields so sector concentration remains usable.
    df["sector"] = df["Industry"]

    df["industry"] = df["Industry"]

    df["active"] = True

    output = df[
        [
            "symbol",
            "company",
            "sector",
            "industry",
            "active",
        ]
    ]

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Atomic replacement.
    temp = OUTPUT.with_suffix(".tmp")

    output.to_csv(
        temp,
        index=False,
    )

    temp.replace(OUTPUT)

    print(
        f"Wrote {len(output)} NIFTY 500 symbols to:"
        f"\n{OUTPUT}"
    )


if __name__ == "__main__":
    main()