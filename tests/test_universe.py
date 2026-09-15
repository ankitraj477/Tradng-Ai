from pathlib import Path
import sys, tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.universe import Universe

def test_universe_deduplicates(tmp_path):
    p=tmp_path/"u.csv"
    p.write_text("symbol,company,sector\nABC.NS,A,IT\nABC.NS,A,IT\nXYZ.NS,X,Bank\n")
    u=Universe(p); rows=u.load()
    assert len(rows)==2
    assert u.symbols()==["ABC.NS","XYZ.NS"]
