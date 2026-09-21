import time

import pandas as pd

from .cache import MarketDataCache
from .manifest import DatasetManifest
from ..universe import Universe
from .validator import validate_history


class YFinanceProvider:
    """
    Yahoo Finance market-data provider.

    Important live-data rules:

    - Live decisions only use fresh data.
    - Stale cached data is never silently used for live decisions.
    - Batch diagnostics retain the reason each requested symbol failed.
    """

    def __init__(
        self,
        symbols=None,
        universe_file="data/nifty500.csv",
        cache=None,
        retries=2,
        max_age_seconds=420,
        min_fresh_data_coverage_pct=0.70,
    ):
        if symbols is None:
            try:
                symbols = [
                    item.symbol
                    for item in Universe(
                        universe_file
                    ).load()
                ]
            except Exception:
                symbols = []

        self._symbols = list(symbols)

        self.cache = cache or MarketDataCache()
        self.manifest = DatasetManifest()

        self.retries = max(
            0,
            int(retries),
        )

        self.max_age_seconds = max(
            1,
            int(max_age_seconds),
        )

        self.min_fresh_data_coverage_pct = min(
            1.0,
            max(
                0.0,
                float(
                    min_fresh_data_coverage_pct
                ),
            ),
        )

        self.last_batch_stats = (
            self._empty_batch_stats()
        )

    def symbols(self):
        return self._symbols

    def _empty_batch_stats(self):
        return {
            "requested": 0,
            "fresh_valid": 0,
            "stale": 0,
            "unavailable": 0,
            "invalid": 0,
            "coverage_pct": 0.0,
            "coverage_ok": False,
            "failed_symbols": [],
            "stale_symbols": [],
            "unavailable_symbols": [],
            "invalid_symbols": [],
        }

    @staticmethod
    def _failure_symbol_list(stats):
        return sorted(
            set(
                stats["stale_symbols"]
            )
            | set(
                stats["unavailable_symbols"]
            )
            | set(
                stats["invalid_symbols"]
            )
        )

    def _download(
        self,
        symbol,
        period,
        interval,
    ):
        import yfinance as yf

        last_error = None

        for attempt in range(
            self.retries + 1
        ):
            try:
                df = yf.download(
                    symbol,
                    period=period,
                    interval=interval,
                    auto_adjust=False,
                    progress=False,
                    threads=False,
                )

                if (
                    df is not None
                    and not df.empty
                ):
                    return df

            except Exception as exc:
                last_error = exc

            if attempt < self.retries:
                time.sleep(
                    0.5 * (attempt + 1)
                )

        if last_error is not None:
            raise last_error

        return None

    @staticmethod
    def _normalize(df):
        if df is None or df.empty:
            return None

        if hasattr(
            df.columns,
            "levels",
        ):
            df = df.copy()

            df.columns = [
                column[0]
                if isinstance(
                    column,
                    tuple,
                )
                else column
                for column in df.columns
            ]

        required = [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        ]

        if not set(required).issubset(
            df.columns
        ):
            return None

        df = (
            df[required]
            .dropna()
            .copy()
        )

        if df.empty:
            return None

        if not isinstance(
            df.index,
            pd.DatetimeIndex,
        ):
            df.index = pd.to_datetime(
                df.index,
                errors="coerce",
            )

        df = df[
            ~df.index.isna()
        ].copy()

        if df.empty:
            return None

        df = df.sort_index()

        return df

    def _validate(
        self,
        df,
        require_fresh=True,
    ):
        return validate_history(
            df,
            max_age_seconds=self.max_age_seconds,
            require_fresh=require_fresh,
        )

    def history(
        self,
        symbol,
        period="60d",
        interval="5m",
    ):
        """
        Return fresh live history.

        A stale price is never returned as a
        live trading input.
        """

        try:
            df = self._download(
                symbol,
                period,
                interval,
            )

            df = self._normalize(df)

            if df is None:
                raise RuntimeError(
                    f"empty or invalid live data "
                    f"for {symbol}"
                )

            ok, message = self._validate(
                df,
                require_fresh=True,
            )

            if not ok:
                raise RuntimeError(
                    "live data rejected for "
                    f"{symbol}: {message}"
                )

            self.cache.save(
                symbol,
                period,
                interval,
                df,
            )

            self.manifest.record(
                "yfinance",
                "ohlcv",
                symbol,
                df.index.min(),
                df.index.max(),
                len(df),
                adjusted=False,
            )

            return df

        except Exception as exc:
            raise RuntimeError(
                "no fresh live data available "
                f"for {symbol}: {exc}"
            ) from exc

    @staticmethod
    def _extract_symbol_frame(
        df,
        symbol,
    ):
        if df is None or df.empty:
            return None

        if not hasattr(
            df.columns,
            "levels",
        ):
            return df.copy()

        levels = df.columns.levels

        for level in range(
            len(levels)
        ):
            values = set(
                levels[level].astype(str)
            )

            if symbol in values:
                try:
                    return df.xs(
                        symbol,
                        axis=1,
                        level=level,
                    ).copy()
                except (
                    KeyError,
                    IndexError,
                ):
                    pass

        return None

    def history_many(
        self,
        symbols,
        period="60d",
        interval="5m",
    ):
        """
        Batch-download many symbols and retain
        diagnostics for every request.

        Returned data contains only symbols that
        independently pass:

        - OHLCV validation
        - timestamp validation
        - freshness validation

        No stale cache is used to fill failures.
        """

        requested = list(
            dict.fromkeys(
                symbols or []
            )
        )

        stats = (
            self._empty_batch_stats()
        )

        stats["requested"] = len(
            requested
        )

        self.last_batch_stats = stats

        if not requested:
            stats["coverage_ok"] = True
            return {}

        try:
            import yfinance as yf

            df = yf.download(
                requested,
                period=period,
                interval=interval,
                auto_adjust=False,
                progress=False,
                threads=True,
                group_by="ticker",
            )

        except Exception as exc:
            stats["unavailable"] = len(
                requested
            )

            stats[
                "unavailable_symbols"
            ] = requested.copy()

            stats[
                "failed_symbols"
            ] = requested.copy()

            stats["coverage_pct"] = 0.0
            stats["coverage_ok"] = False
            stats["error"] = repr(exc)

            return {}

        if df is None or df.empty:
            stats["unavailable"] = len(
                requested
            )

            stats[
                "unavailable_symbols"
            ] = requested.copy()

            stats[
                "failed_symbols"
            ] = requested.copy()

            stats["coverage_pct"] = 0.0
            stats["coverage_ok"] = False

            return {}

        output = {}

        for symbol in requested:
            try:
                part = (
                    self._extract_symbol_frame(
                        df,
                        symbol,
                    )
                )

                if part is None:
                    stats[
                        "unavailable"
                    ] += 1

                    stats[
                        "unavailable_symbols"
                    ].append(symbol)

                    continue

                part = self._normalize(
                    part
                )

                if part is None:
                    stats[
                        "invalid"
                    ] += 1

                    stats[
                        "invalid_symbols"
                    ].append(symbol)

                    continue

                ok, message = (
                    self._validate(
                        part,
                        require_fresh=True,
                    )
                )

                if not ok:
                    message = str(
                        message
                    )

                    if message.startswith(
                        "stale data:"
                    ):
                        stats[
                            "stale"
                        ] += 1

                        stats[
                            "stale_symbols"
                        ].append(symbol)

                    else:
                        stats[
                            "invalid"
                        ] += 1

                        stats[
                            "invalid_symbols"
                        ].append(symbol)

                    continue

                self.cache.save(
                    symbol,
                    period,
                    interval,
                    part,
                )

                self.manifest.record(
                    "yfinance",
                    "ohlcv",
                    symbol,
                    part.index.min(),
                    part.index.max(),
                    len(part),
                    adjusted=False,
                )

                output[symbol] = part

            except Exception:
                if (
                    symbol
                    not in self._failure_symbol_list(
                        stats
                    )
                ):
                    stats[
                        "unavailable"
                    ] += 1

                    stats[
                        "unavailable_symbols"
                    ].append(symbol)

        stats[
            "fresh_valid"
        ] = len(output)

        stats[
            "failed_symbols"
        ] = sorted(
            set(
                stats[
                    "stale_symbols"
                ]
            )
            | set(
                stats[
                    "unavailable_symbols"
                ]
            )
            | set(
                stats[
                    "invalid_symbols"
                ]
            )
        )

        stats[
            "coverage_pct"
        ] = (
            stats["fresh_valid"]
            / stats["requested"]
            if stats["requested"]
            else 1.0
        )

        stats[
            "coverage_ok"
        ] = (
            stats["coverage_pct"]
            >= self.min_fresh_data_coverage_pct
        )

        self.last_batch_stats = stats

        return output

    def quote(self, symbol):
        """
        Return the latest fresh 5-minute quote.

        Stale cached data is never returned.
        """

        df = self.history(
            symbol,
            period="5d",
            interval="5m",
        )

        if df is None or df.empty:
            raise RuntimeError(
                f"no quote data available "
                f"for {symbol}"
            )

        timestamp = df.index[-1]

        if getattr(
            timestamp,
            "tzinfo",
            None,
        ) is None:
            timestamp = timestamp.tz_localize(
                "UTC"
            )

        return {
            "symbol": symbol,
            "price": float(
                df["Close"].iloc[-1]
            ),
            "timestamp": (
                timestamp.to_pydatetime()
            ),
        }