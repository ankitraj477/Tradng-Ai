import pandas as pd
import numpy as np
from app.scanner import Scanner

class Provider:
    def __init__(self):
        self.calls=0
        self.df=pd.DataFrame({
            'Open':np.linspace(100,110,80),'High':np.linspace(101,111,80),
            'Low':np.linspace(99,109,80),'Close':np.linspace(100,110,80),
            'Volume':np.full(80,1000.0)
        })
    def symbols(self): return ['A','B']
    def metadata(self): return {}
    def history_many(self,symbols): self.calls+=1; return {s:self.df for s in symbols}
    def history(self,symbol): raise AssertionError('batch path should be used')

def test_scanner_uses_batch_history():
    p=Provider(); rows=Scanner(10).scan(p,1000)
    assert p.calls==1
    assert isinstance(rows,list)
