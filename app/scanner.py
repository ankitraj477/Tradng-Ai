import csv
import shutil
import subprocess
import tempfile
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

        if len(order) != len(rows):
            raise RuntimeError(
                "C++ scanner returned incomplete output"
            )

        return sorted(
            rows,
            key=lambda row: order[row["symbol"]],
        )

    def scan(self, provider, cash):
        rows = []

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

                score = 0

                if (
                    row["Close"]
                    > row["ema20"]
                    > row["ema50"]
                ):
                    score += 30

                if row["rsi"] > 55:
                    score += 15

                if row["rel_volume"] > 1.2:
                    score += 20

                if row["ret_5"] > 0:
                    score += 15

                if row["ret_20"] > 0:
                    score += 10

                if row["Close"] > row["vwap"]:
                    score += 10

                rows.append(
                    {
                        "symbol": symbol,
                        "price": float(
                            row["Close"]
                        ),
                        "score": float(score),
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

            except Exception:
                continue

        if self.use_cpp:
            rows = self._rank_cpp(rows)
        else:
            rows.sort(
                key=lambda row: row["score"],
                reverse=True,
            )

        return rows[:self.max_candidates]