from .yfinance_provider import YFinanceProvider
from ..universe import Universe

class Nifty500Provider(YFinanceProvider):
    """Provider backed by the local, explicitly imported NIFTY 500 universe."""
    def __init__(self, universe_file="data/nifty500.csv"):
        rows=Universe(universe_file).load()
        super().__init__([x.symbol for x in rows], universe_file=universe_file)
