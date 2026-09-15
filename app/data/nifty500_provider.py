from .yfinance_provider import YFinanceProvider
from ..universe import Universe
from pathlib import Path

class Nifty500Provider(YFinanceProvider):
    """Provider backed by the locally imported NIFTY 500 universe."""
    def __init__(self, universe_file="data/nifty500.csv"):
        if not Path(universe_file).is_absolute():
            universe_file = str(Path(__file__).resolve().parents[2] / universe_file)
        self.universe=Universe(universe_file)
        rows=self.universe.load()
        super().__init__([x.symbol for x in rows], universe_file=universe_file)

    def metadata(self):
        return self.universe.metadata()
