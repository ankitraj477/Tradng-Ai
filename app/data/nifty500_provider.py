from pathlib import Path

from .yfinance_provider import YFinanceProvider
from ..universe import Universe


class Nifty500Provider(YFinanceProvider):
    """
    NIFTY 500 universe backed by the local normalized CSV.

    The universe is local; market data is fetched from yfinance.
    """

    def __init__(
        self,
        universe_file="data/nifty500.csv",
        max_age_seconds=420,
        min_fresh_data_coverage_pct=0.70,
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
            symbols=self.universe.symbols(),
            universe_file=universe_file,
            max_age_seconds=max_age_seconds,
            min_fresh_data_coverage_pct=(
                min_fresh_data_coverage_pct
            ),
        )

    def reload_universe(self):
        """Reload the current NIFTY 500 universe from disk."""
        self.universe.load()
        self._symbols = self.universe.symbols()
        return len(self._symbols)

    def metadata(self):
        return self.universe.metadata()