from pathlib import Path

from app.universe import Universe


def test_universe_validation_accepts_current_nifty500_universe():
    universe_file = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "nifty500.csv"
    )

    universe = Universe(universe_file)
    universe.load()

    ok, count = universe.validate(450)

    assert ok
    assert count >= 450