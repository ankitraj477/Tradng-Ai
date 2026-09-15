"""
Update the local NIFTY 500 universe from a CSV you download from the official
NSE/Nifty Indices page. This script intentionally does not scrape undocumented
endpoints or bypass access controls.

Expected input columns:
symbol, company, sector, industry

Example:
python scripts/update_universe.py path/to/nifty500.csv
"""
import sys, shutil
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if len(sys.argv)!=2:
    raise SystemExit("Usage: python scripts/update_universe.py <downloaded_nifty500.csv>")

src=Path(sys.argv[1])
if not src.exists(): raise SystemExit(f"Not found: {src}")
df=pd.read_csv(src)
if "symbol" not in df.columns:
    raise SystemExit("CSV needs a symbol column")

out=ROOT/"data"/"nifty500.csv"
out.parent.mkdir(exist_ok=True)
df.to_csv(out,index=False)
print(f"Wrote {len(df)} symbols to {out}")
