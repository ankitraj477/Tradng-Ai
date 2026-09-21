from pathlib import Path

from .yfinance_provider import YFinanceProvider
from ..universe import Universe


class Nifty500Provider(YFinanceProvider):
    """Provider backed by the local NIFTY 500 universe."""

    def __init__(
        self,
        universe_file="data/nifty500.csv",
    ):
        if not Path(universe_file).is_absolute():
            universe_file = str(
                Path(__file__).resolve().parents[2]
                / universe_file
            )

        self.universe = Universe(universe_file)
        self.universe_file = universe_file

        self.universe.load()

        super().__init__(
            self.universe.symbols(),
            universe_file=universe_file,
        )

    def reload_universe(self):
        self.universe.load()
        self._symbols = self.universe.symbols()
        return len(self._symbols)

    def metadata(self):
        return self.universe.metadata()