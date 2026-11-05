import csv
import shutil
import subprocess
import tempfile
from itertools import zip_longest
from pathlib import Path

from .indicators import indicators


class Scanner:
    def __init__(
        self,
        max_candidates=50,
        use_cpp=False,
        cpp_path="",
    ):
        self.max_candidates = max_candidates
        self.use_cpp = use_cpp
        self.cpp_path = cpp_path

    def _cpp_executable(self):
        if not self.use_cpp:
            return None

        candidates = []

        if self.cpp_path:
            candidates.append(
                Path(self.cpp_path)
            )

        root = (
            Path(__file__)
            .resolve()
            .parent.parent
        )

        candidates.extend(
            [
                root / "cpp" / "scanner.exe",
                root / "cpp" / "scanner",
            ]
        )

        system_scanner = shutil.which("scanner")

        if system_scanner:
            candidates.append(
                Path(system_scanner)
            )

        return next(
            (
                path
                for path in candidates
                if path.exists()
            ),
            None,
        )

    def _rank_cpp(self, rows):
        executable = self._cpp_executable()

        if executable is None:
            raise RuntimeError(
                "USE_CPP_SCANNER=true but no compiled "
                "scanner was found. Build cpp/scanner.exe "
                "or set CPP_SCANNER_PATH."
            )

        with tempfile.TemporaryDirectory(
            prefix="ai_trader_scan_"
        ) as tmp:

            input_path = (
                Path(tmp) / "scan.csv"
            )

            with input_path.open(
                "w",
                newline="",
                encoding="utf-8",
            ) as file:

                writer = csv.writer(file)

                writer.writerow(
                    [
                        "symbol",
                        "price",
                        "rsi",
                        "relvol",
                        "ret5",
                        "ret20",
                    ]
                )

                for row in rows:
                    writer.writerow(
                        [
                            row["symbol"],
                            row["price"],
                            row["rsi"],
                            row["rel_volume"],
                            row["ret_5"],
                            row["ret_20"],
                        ]
                    )

            result = subprocess.run(
                [
                    str(executable),
                    str(input_path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )

        order = {}

        for rank, line in enumerate(
            result.stdout.splitlines()[1:]
        ):
            parts = line.split(",")

            if parts:
                order[
                    parts[0].strip()
                ] = rank

        if not order and rows:
            raise RuntimeError(
                "C++ scanner returned incomplete output"
            )

        return sorted(
            rows,
            key=lambda row: order.get(row["symbol"], 999999),
        )

    def scan(self, provider, cash):
        rows = []
        # BUG-029: Count failures per scan cycle
        _scan_failures = 0

        metadata = (
            provider.metadata()
            if hasattr(provider, "metadata")
            else {}
        )

        histories = (
            provider.history_many(
                provider.symbols()
            )
            if hasattr(provider, "history_many")
            else {}
        )

        for symbol in provider.symbols():
            try:
                df = (
                    histories.get(symbol)
                    if histories
                    else provider.history(symbol)
                )

                if df is None or len(df) < 60:
                    continue

                data = indicators(df)

                if data.empty:
                    continue

                row = data.iloc[-1]

                bull_score = 0
                bear_score = 0

                if row["Close"] > row["ema20"] > row["ema50"]:
                    bull_score += 30
                elif row["Close"] < row["ema20"] < row["ema50"]:
                    bear_score += 30

                if row["rsi"] > 55:
                    bull_score += 15
                elif row["rsi"] < 45:
                    bear_score += 15

                if row["rel_volume"] > 1.2:
                    bull_score += 20
                    bear_score += 20

                if row["ret_5"] > 0:
                    bull_score += 15
                elif row["ret_5"] < 0:
                    bear_score += 15

                if row["ret_20"] > 0:
                    bull_score += 10
                elif row["ret_20"] < 0:
                    bear_score += 10

                if row["Close"] > row["vwap"]:
                    bull_score += 10
                elif row["Close"] < row["vwap"]:
                    bear_score += 10

                score = max(bull_score, bear_score)

                rows.append(
                    {
                        "symbol": symbol,
                        "price": float(
                            row["Close"]
                        ),
                        "score": float(score),
                        "bull_score": float(bull_score),
                        "bear_score": float(bear_score),
                        "rsi": float(
                            row["rsi"]
                        ),
                        "atr": float(
                            row["atr"]
                        ),
                        "rel_volume": float(
                            row["rel_volume"]
                        ),
                        "ret_5": float(
                            row["ret_5"]
                        ),
                        "ret_20": float(
                            row["ret_20"]
                        ),
                        "volatility": float(
                            row["volatility"]
                        ),
                        "sector": getattr(
                            metadata.get(symbol),
                            "sector",
                            "Unknown",
                        ),
                    }
                )

            except Exception as exc:
                # BUG-029: Count and log scanner failures instead of silently swallowing
                _scan_failures += 1
                if _scan_failures <= 5:  # Log first 5 failures in detail
                    import logging
                    logging.getLogger("tradng_ai.scanner").debug(
                        f"Scanner error for {symbol}: {exc!r}"
                    )
                continue

        # BUG-029: Log aggregate failure count
        if _scan_failures > 0:
            import logging
            logging.getLogger("tradng_ai.scanner").warning(
                f"Scanner cycle: {_scan_failures} symbol(s) failed out of {len(provider.symbols())}"
            )

        if self.use_cpp:
            rows = self._rank_cpp(rows)
        else:
            bulls = sorted([r for r in rows if r["bull_score"] >= r["bear_score"]], key=lambda r: r["bull_score"], reverse=True)
            bears = sorted([r for r in rows if r["bear_score"] > r["bull_score"]], key=lambda r: r["bear_score"], reverse=True)
            rows = [x for pair in zip_longest(bulls, bears) for x in pair if x]

        return rows[:self.max_candidates]