from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.learning import LearningEngine
class D:
    def all_trades(self):
        return [{"strategy":"Momentum","pnl":10},{"strategy":"Momentum","pnl":-2}]
def test_learning_waits_for_sample():
    x=LearningEngine(D()).weights(minimum_sample=20)
    assert x["Momentum"]==1.0
