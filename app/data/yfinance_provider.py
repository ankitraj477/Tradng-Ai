import time
from pathlib import Path

import pandas as pd

from .cache import MarketDataCache
from .manifest import DatasetManifest
from .provider import MarketDataProvider
from .validator import validate_history
from ..universe import Universe


class YFinanceProvider(MarketDataProvider):
    """
    Free public market-data provider using yfinance.

    Live-trading safety:
    - Only valid OHLCV data is accepted.
    - Live data must pass the freshness check.
    - Stale cached data is never silently used for live decisions.
    - Full-universe downloads are split into small chunks.
    - Every requested symbol gets a diagnostic classification.
    """

    def __init__(
        self,
        symbols=None,
        universe_file="data/nifty500.csv",
        cache=None,
        retries=2,
        max_age_seconds=420,
        min_fresh_data_coverage_pct=0.70,
        batch_size=50,
        batch_period="5d",
        batch_interval="5m",
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

        self.cache = (
            cache or MarketDataCache()
        )

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

        self.batch_size = max(
            1,
            int(batch_size),
        )

        self.batch_period = str(
            batch_period
        )

        self.batch_interval = str(
            batch_interval
        )

        self.last_batch_stats = (
            self._empty_batch_stats(0)
        )

    def symbols(self):
        return self._symbols

    # ======================================================
    # BATCH DIAGNOSTICS
    # ======================================================

    @staticmethod
    def _empty_batch_stats(
        requested
    ):
        return {
            "requested": int(
                requested
            ),
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

    def _record_failure(
        self,
        stats,
        symbol,
        kind,
    ):
        stats[kind] += 1
        stats[
            f"{kind}_symbols"
        ].append(symbol)

    # ======================================================
    # DATA NORMALIZATION
    # ======================================================

    @staticmethod
    def _normalize(df):
        if (
            df is None
            or df.empty
        ):
            return None

        required = {
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        }

        # yfinance can return either:
        #
        # ('Ticker', 'Price')
        #
        # or:
        #
        # ('Price', 'Ticker')
        #
        # depending on the request/version.
        if isinstance(
            df.columns,
            pd.MultiIndex,
        ):
            flattened = []

            for column in df.columns:
                chosen = None

                for value in column:
                    value = str(value)

                    if value in required:
                        chosen = value
                        break

                flattened.append(
                    chosen
                    if chosen is not None
                    else str(
                        column[-1]
                    )
                )

            df = df.copy()
            df.columns = flattened

        else:
            df = df.copy()

            df.columns = [
                str(column)
                for column in df.columns
            ]

        if not required.issubset(
            df.columns
        ):
            return None

        df = (
            df[
                [
                    "Open",
                    "High",
                    "Low",
                    "Close",
                    "Volume",
                ]
            ]
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

        # Normalize timestamps to UTC.
        if (
            getattr(
                df.index,
                "tz",
                None,
            )
            is None
        ):
            df.index = (
                df.index.tz_localize(
                    "UTC"
                )
            )
        else:
            df.index = (
                df.index.tz_convert(
                    "UTC"
                )
            )

        df = df.sort_index()

        return df

    def _validate(
        self,
        df,
        require_fresh=True,
    ):
        return validate_history(
            df,
            max_age_seconds=(
                self.max_age_seconds
            ),
            require_fresh=(
                require_fresh
            ),
        )

    # ======================================================
    # SINGLE SYMBOL DOWNLOAD
    # ======================================================

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

            if (
                attempt
                < self.retries
            ):
                time.sleep(
                    0.5
                    * (attempt + 1)
                )

        if last_error is not None:
            raise last_error

        return None

    # ======================================================
    # SINGLE SYMBOL HISTORY
    # ======================================================

    def history(
        self,
        symbol,
        period="60d",
        interval="5m",
    ):
        """
        Return fresh live history.

        Stale cached data is NEVER used as a
        replacement for fresh live data.
        """

        try:
            df = self._download(
                symbol,
                period,
                interval,
            )

            df = self._normalize(
                df
            )

            if df is None:
                raise RuntimeError(
                    "empty or invalid "
                    f"live data for {symbol}"
                )

            ok, message = (
                self._validate(
                    df,
                    require_fresh=True,
                )
            )

            if not ok:
                raise RuntimeError(
                    "live data rejected "
                    f"for {symbol}: "
                    f"{message}"
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
                "no fresh live data "
                f"available for {symbol}: "
                f"{exc}"
            ) from exc

    # ======================================================
    # EXTRACT ONE SYMBOL FROM BATCH
    # ======================================================

    @staticmethod
    def _extract_symbol_frame(
        df,
        symbol,
    ):
        if (
            df is None
            or df.empty
        ):
            return None

        if isinstance(
            df.columns,
            pd.MultiIndex,
        ):
            for level in range(
                df.columns.nlevels
            ):
                values = {
                    str(value)
                    for value in (
                        df.columns
                        .get_level_values(
                            level
                        )
                    )
                }

                if symbol not in values:
                    continue

                try:
                    part = df.xs(
                        symbol,
                        axis=1,
                        level=level,
                    )

                    return part.copy()

                except (
                    KeyError,
                    IndexError,
                ):
                    continue

            return None

        return df.copy()

    # ======================================================
    # CHUNK DOWNLOAD
    # ======================================================

    def _download_many_chunk(
        self,
        symbols,
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
                    symbols,
                    period=period,
                    interval=interval,
                    auto_adjust=False,
                    progress=False,
                    threads=True,
                    group_by="ticker",
                )

                if (
                    df is not None
                    and not df.empty
                ):
                    return df

            except Exception as exc:
                last_error = exc

            if (
                attempt
                < self.retries
            ):
                time.sleep(
                    0.5
                    * (attempt + 1)
                )

        if last_error is not None:
            raise last_error

        return None

    @staticmethod
    def _is_stale_failure(
        message
    ):
        return str(
            message
        ).startswith(
            "stale data:"
        )

    # ======================================================
    # BATCH HISTORY
    # ======================================================

    def history_many(
        self,
        symbols,
        period=None,
        interval=None,
    ):
        """
        Fetch many symbols using small yfinance chunks.

        Default live scanner request:

            5 days
            5 minute bars
            50 symbols per batch

        This is intentionally different from history(),
        because the scanner needs recent intraday bars rather
        than 60 days of data for every symbol on every cycle.

        No stale cache fallback is allowed.
        """

        requested = list(
            dict.fromkeys(
                symbols or []
            )
        )

        period = str(
            period
            or self.batch_period
        )

        interval = str(
            interval
            or self.batch_interval
        )

        stats = (
            self._empty_batch_stats(
                len(requested)
            )
        )

        self.last_batch_stats = stats

        if not requested:
            stats[
                "coverage_pct"
            ] = 1.0

            stats[
                "coverage_ok"
            ] = True

            return {}

        output = {}

        # --------------------------------------------------
        # PROCESS SMALL CHUNKS
        # --------------------------------------------------

        for start in range(
            0,
            len(requested),
            self.batch_size,
        ):
            chunk = requested[
                start:
                start + self.batch_size
            ]

            try:
                raw = (
                    self._download_many_chunk(
                        chunk,
                        period,
                        interval,
                    )
                )

            except Exception:
                # Entire failed chunk is considered
                # unavailable.
                #
                # We deliberately do not use cache here.
                for symbol in chunk:
                    self._record_failure(
                        stats,
                        symbol,
                        "unavailable",
                    )

                continue

            # --------------------------------------------------
            # VALIDATE EVERY SYMBOL IN THE CHUNK
            # --------------------------------------------------

            for symbol in chunk:

                try:
                    part = (
                        self._extract_symbol_frame(
                            raw,
                            symbol,
                        )
                    )

                    if (
                        part is None
                        or part.empty
                    ):
                        self._record_failure(
                            stats,
                            symbol,
                            "unavailable",
                        )

                        continue

                    normalized = (
                        self._normalize(
                            part
                        )
                    )

                    if (
                        normalized is None
                    ):
                        self._record_failure(
                            stats,
                            symbol,
                            "unavailable",
                        )

                        continue

                    ok, message = (
                        self._validate(
                            normalized,
                            require_fresh=True,
                        )
                    )

                    if not ok:

                        if (
                            self._is_stale_failure(
                                message
                            )
                        ):
                            self._record_failure(
                                stats,
                                symbol,
                                "stale",
                            )
                        else:
                            self._record_failure(
                                stats,
                                symbol,
                                "invalid",
                            )

                        continue

                    # --------------------------------------------------
                    # FRESH DATA ONLY
                    # --------------------------------------------------

                    self.cache.save(
                        symbol,
                        period,
                        interval,
                        normalized,
                    )

                    self.manifest.record(
                        "yfinance",
                        "ohlcv",
                        symbol,
                        normalized.index.min(),
                        normalized.index.max(),
                        len(normalized),
                        adjusted=False,
                    )

                    output[
                        symbol
                    ] = normalized

                    stats[
                        "fresh_valid"
                    ] += 1

                except Exception:
                    self._record_failure(
                        stats,
                        symbol,
                        "unavailable",
                    )

        # --------------------------------------------------
        # FINAL DIAGNOSTICS
        # --------------------------------------------------

        stats[
            "failed_symbols"
        ] = sorted(
            set(
                stats[
                    "stale_symbols"
                ]
            )
            |
            set(
                stats[
                    "unavailable_symbols"
                ]
            )
            |
            set(
                stats[
                    "invalid_symbols"
                ]
            )
        )

        stats[
            "coverage_pct"
        ] = (
            stats[
                "fresh_valid"
            ]
            / stats[
                "requested"
            ]
            if stats[
                "requested"
            ]
            else 1.0
        )

        stats[
            "coverage_ok"
        ] = (
            stats[
                "coverage_pct"
            ]
            >= self.min_fresh_data_coverage_pct
        )

        self.last_batch_stats = (
            stats
        )

        return output

    # ======================================================
    # QUOTE
    # ======================================================

    def quote(
        self,
        symbol,
    ):
        """
        Return the latest fresh 5-minute quote.

        Stale cached data is never returned.
        """

        df = self.history(
            symbol,
            period="5d",
            interval="5m",
        )

        if (
            df is None
            or df.empty
        ):
            raise RuntimeError(
                "no quote data "
                f"available for {symbol}"
            )

        timestamp = (
            df.index[-1]
        )

        if (
            getattr(
                timestamp,
                "tzinfo",
                None,
            )
            is None
        ):
            timestamp = (
                timestamp.tz_localize(
                    "UTC"
                )
            )
        else:
            timestamp = (
                timestamp.tz_convert(
                    "UTC"
                )
            )

        return {
            "symbol": symbol,
            "price": float(
                df[
                    "Close"
                ].iloc[-1]
            ),
            "timestamp": (
                timestamp.to_pydatetime()
            ),
        }