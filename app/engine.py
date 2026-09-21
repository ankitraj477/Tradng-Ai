import time

from .config import load_config
from .db import DB
from .market_hours import (
    market_open,
    market_phase,
    holiday_name,
)
from .data.demo_provider import DemoProvider
from .data.nifty500_provider import Nifty500Provider
from .data.validator import validate_history
from .indicators import indicators
from .scanner import Scanner
from .ai_trader import AITrader
from .portfolio import PortfolioManager
from .risk import RiskManager
from .execution import PaperExecution
from .regime import detect
from .learning import LearningEngine
from .news import NewsProvider
from .market_intelligence import MarketIntelligence
from .position_manager import PositionManager
from .selection import CandidateSelector
from .accounting import portfolio_metrics
from .runtime import preflight


class TradingEngine:

    def __init__(self, live=False):
        self.cfg = load_config()

        # live=True enables live MARKET DATA only.
        # Execution remains paper-only.
        self.cfg["live_data"] = (
            live or self.cfg["live_data"]
        )

        self.db = DB(
            self.cfg["database_path"]
        )

        self.db.ensure_account(
            self.cfg["capital"]["starting"],
            self.cfg["capital"]["target"],
        )

        # --------------------------------------------------
        # DATA PROVIDER
        # --------------------------------------------------

        if self.cfg["live_data"]:
            market_cfg = self.cfg["market"]

            self.provider = Nifty500Provider(
                max_age_seconds=market_cfg.get(
                    "live_data_max_age_seconds",
                    420,
                ),
                min_fresh_data_coverage_pct=market_cfg.get(
                    "min_fresh_data_coverage_pct",
                    0.70,
                ),
            )
        else:
            self.provider = DemoProvider()

        # --------------------------------------------------
        # NIFTY 500 UNIVERSE GUARD
        # --------------------------------------------------

        self.universe_ready = True
        self.universe_reason = "demo universe"

        if self.cfg["live_data"]:
            self.refresh_universe_guard()

        # --------------------------------------------------
        # CORE COMPONENTS
        # --------------------------------------------------

        self.scanner = Scanner(
            self.cfg["market"]["max_candidates"],
            self.cfg["use_cpp_scanner"],
            self.cfg.get(
                "cpp_scanner_path",
                "",
            ),
        )

        self.learning = LearningEngine(
            self.db,
            self.cfg,
        )

        self.news = NewsProvider()

        self.intel = MarketIntelligence(
            self.news
        )

        self.ai = AITrader(
            self.learning
        )

        self.pm = PortfolioManager(
            self.db,
            self.cfg,
        )

        self.risk = RiskManager(
            self.db,
            self.cfg,
        )

        # Paper-only execution.
        self.exec = PaperExecution(
            self.db,
            self.cfg,
        )

        self.positions = PositionManager(
            self.db,
            self.exec,
            self.provider,
            self.cfg,
        )

        self.selector = CandidateSelector(
            self.learning,
            self.cfg["risk"].get(
                "max_sector_exposure_pct",
                0.40,
            ),
        )

        self.preflight = preflight(
            self.cfg,
            self.provider,
        )

    # ======================================================
    # UNIVERSE
    # ======================================================

    def refresh_universe_guard(self):
        """
        Re-check the NIFTY 500 universe.

        Live paper trading requires at least 450
        active constituents.
        """

        if not self.cfg["live_data"]:
            self.universe_ready = True
            self.universe_reason = (
                "demo universe"
            )
            return

        try:

            if hasattr(
                self.provider,
                "reload_universe",
            ):
                self.provider.reload_universe()

            if hasattr(
                self.provider,
                "universe",
            ):
                ok, count = (
                    self.provider.universe.validate(
                        450
                    )
                )
            else:
                ok, count = False, 0

            self.universe_ready = ok

            if ok:
                self.universe_reason = (
                    f"{count} NIFTY 500 "
                    "constituents loaded"
                )
            else:
                self.universe_reason = (
                    f"{count} constituents loaded; "
                    "need at least 450"
                )

        except Exception as exc:

            self.universe_ready = False

            self.universe_reason = repr(
                exc
            )

    # ======================================================
    # LIVE DATA DIAGNOSTICS
    # ======================================================

    def _log_live_data_stats(self):
        """
        Log diagnostics produced by the latest
        live history_many() request.
        """

        if not self.cfg["live_data"]:
            return

        stats = getattr(
            self.provider,
            "last_batch_stats",
            None,
        )

        if not stats:
            return

        requested = int(
            stats.get(
                "requested",
                0,
            )
        )

        fresh = int(
            stats.get(
                "fresh_valid",
                0,
            )
        )

        stale = int(
            stats.get(
                "stale",
                0,
            )
        )

        unavailable = int(
            stats.get(
                "unavailable",
                0,
            )
        )

        invalid = int(
            stats.get(
                "invalid",
                0,
            )
        )

        coverage = float(
            stats.get(
                "coverage_pct",
                0.0,
            )
        )

        self.db.log(
            "INFO",
            "LIVE DATA: "
            f"requested={requested} "
            f"fresh={fresh} "
            f"stale={stale} "
            f"unavailable={unavailable} "
            f"invalid={invalid} "
            f"coverage={coverage * 100:.1f}%",
        )

    # ======================================================
    # FRESH DATA COVERAGE
    # ======================================================

    def _fresh_data_coverage_ok(self):
        """
        Check whether enough of the requested universe
        has fresh valid market data.

        This only controls NEW trades.
        Existing positions are managed separately.
        """

        if not self.cfg["live_data"]:
            return True, "demo data"

        stats = getattr(
            self.provider,
            "last_batch_stats",
            None,
        )

        if not stats:
            return (
                False,
                "no live-data batch diagnostics available",
            )

        requested = int(
            stats.get(
                "requested",
                0,
            )
        )

        fresh = int(
            stats.get(
                "fresh_valid",
                0,
            )
        )

        coverage = float(
            stats.get(
                "coverage_pct",
                0.0,
            )
        )

        minimum = float(
            self.cfg["market"].get(
                "min_fresh_data_coverage_pct",
                0.70,
            )
        )

        if requested <= 0:
            return (
                False,
                "live-data batch requested zero symbols",
            )

        if coverage < minimum:
            return (
                False,
                (
                    "fresh-data coverage below minimum: "
                    f"{fresh}/{requested} "
                    f"({coverage * 100:.1f}%) < "
                    f"{minimum * 100:.1f}%"
                ),
            )

        return True, "ok"

    # ======================================================
    # MARKET CONTEXT
    # ======================================================

    def market_context(self):

        try:

            df = self.provider.history(
                "^NSEI",
                period=self.cfg[
                    "market"
                ].get(
                    "history_period",
                    "60d",
                ),
                interval="5m",
            )

            ok, msg = validate_history(
                df,
                self.cfg[
                    "market"
                ][
                    "data_max_age_seconds"
                ],
            )

            if not ok:

                return {
                    "ok": False,
                    "reason": msg,
                    **detect(None),
                    "news_items": [],
                }

            x = indicators(df)

            if x.empty:

                return {
                    "ok": False,
                    "reason": (
                        "insufficient "
                        "indicator data"
                    ),
                    **detect(None),
                    "news_items": [],
                }

            metadata = (
                self.provider.metadata()
                if hasattr(
                    self.provider,
                    "metadata",
                )
                else {}
            )

            return {
                "ok": True,
                "reason": "ok",
                **self.intel.build(
                    x.iloc[-1].to_dict(),
                    metadata,
                ),
            }

        except Exception as exc:

            return {
                "ok": False,
                "reason": repr(exc),
                **detect(None),
                "news_items": [],
            }

    # ======================================================
    # ONE TRADING CYCLE
    # ======================================================

    def cycle(self):

        # --------------------------------------------------
        # MARKET CLOSED
        # --------------------------------------------------
        #
        # IMPORTANT:
        # Check market status BEFORE requesting fresh
        # live 5-minute data.
        #
        # After NSE closes, yesterday's/latest session
        # candle will naturally become older than the
        # live freshness threshold.
        #
        # That is normal and must not be treated as a
        # live-data outage.
        # --------------------------------------------------

        if (
            self.cfg["live_data"]
            and not market_open()
        ):

            phase = market_phase()
            holiday = holiday_name()

            self.db.set_market(
                "CLOSED",
                "N/A",
                None,
                True,
            )

            self.db.log(
                "INFO",
                "Indian market "
                f"{phase.lower()}: "
                "analysis/preparation cycle."
                + (
                    f" Holiday={holiday}"
                    if holiday
                    else ""
                ),
            )

            self.db.log(
                "INFO",
                "Learning snapshot: "
                f"{self.learning.recommendation()}",
            )

            self.db.log(
                "INFO",
                "News items available: "
                "market closed",
            )

            self.snapshot()

            return

        # --------------------------------------------------
        # REVALIDATE LIVE UNIVERSE
        # --------------------------------------------------

        if self.cfg["live_data"]:
            self.refresh_universe_guard()

        # --------------------------------------------------
        # UNIVERSE KILL SWITCH
        # --------------------------------------------------

        if (
            self.cfg["live_data"]
            and not self.universe_ready
        ):

            self.db.log(
                "ERROR",
                "UNIVERSE KILL SWITCH: "
                f"{self.universe_reason}. "
                "Update data/nifty500.csv before "
                "live paper trading.",
            )

            self.snapshot()

            return

        # --------------------------------------------------
        # MARKET CONTEXT
        # --------------------------------------------------

        ctx = self.market_context()

        self.db.set_market(
            ctx["regime"],
            ctx["sentiment"],
            ctx["nifty"],
            ctx["ok"],
        )

        # --------------------------------------------------
        # DATA KILL SWITCH
        # --------------------------------------------------

        if (
            self.cfg["live_data"]
            and not ctx["ok"]
        ):

            self.db.log(
                "WARN",
                "DATA KILL SWITCH: "
                f"{ctx['reason']}",
            )

            self.snapshot()

            return

        # --------------------------------------------------
        # RISK GATE
        # --------------------------------------------------

        allowed, why = (
            self.risk.trading_allowed()
        )

        # Existing positions are always handled separately.
        self.positions.manage()

        if not allowed:

            self.db.log(
                "WARN",
                f"TRADING BLOCKED: {why}",
            )

            self.snapshot()

            return

        # --------------------------------------------------
        # CANDIDATE SCAN
        # --------------------------------------------------

        account = self.db.account()

        candidates = self.scanner.scan(
            self.provider,
            account["cash"],
        )

        # Scanner uses provider.history_many().
        # The provider should have populated last_batch_stats.
        if self.cfg["live_data"]:

            self._log_live_data_stats()

            coverage_ok, coverage_reason = (
                self._fresh_data_coverage_ok()
            )

            if not coverage_ok:

                self.db.log(
                    "WARN",
                    "FRESH-DATA COVERAGE GATE: "
                    f"{coverage_reason}. "
                    "No new trades.",
                )

                self.snapshot()

                return

        # --------------------------------------------------
        # ENRICH CANDIDATES
        # --------------------------------------------------

        enriched = [
            self.intel.enrich(
                candidate,
                ctx,
            )
            for candidate in candidates
        ]

        if not enriched:

            self.db.log(
                "INFO",
                "No candidates.",
            )

            self.snapshot()

            return

        # --------------------------------------------------
        # AI PROPOSALS
        # --------------------------------------------------

        proposals = []

        for candidate in enriched[
            :min(20, len(enriched))
        ]:

            proposal = self.ai.propose(
                candidate,
                ctx["regime"],
                ctx["sentiment"],
            )

            proposal["score"] = candidate.get(
                "score",
                0,
            )

            decision = "PENDING"
            qty = 0

            if proposal["action"] in {
                "BUY",
                "SHORT",
            }:

                qty = self.pm.size(
                    proposal
                )

                decision = self.risk.approve(
                    proposal,
                    qty,
                )

                if decision == "APPROVE":
                    proposals.append(
                        (
                            proposal,
                            qty,
                        )
                    )

            # Persist every AI decision.
            self.db.add_decision(
                {
                    **proposal,
                    "risk_decision": decision,
                }
            )

        # --------------------------------------------------
        # PORTFOLIO-AWARE SELECTION
        # --------------------------------------------------

        if proposals:

            ranked_inputs = []

            for proposal, qty in proposals:

                ranked_inputs.append(
                    {
                        **proposal,
                        "best_strategy":
                            proposal["strategy"],
                        "qty": qty,
                        "current_price":
                            proposal["price"],
                    }
                )

            ranked = self.selector.rank(
                ranked_inputs,
                self.db.positions(),
                ctx["regime"],
                self.pm.metrics()["equity"],
            )

            if ranked:

                chosen = ranked[0]

                proposal, qty = next(
                    (
                        item
                        for item in proposals
                        if item[0]["symbol"]
                        == chosen["symbol"]
                    ),
                    (None, 0),
                )

                if proposal:

                    # --------------------------------------
                    # PAPER EXECUTION ONLY
                    # --------------------------------------

                    if proposal["action"] == "BUY":

                        ok = self.exec.buy(
                            proposal,
                            qty,
                            ctx["regime"],
                        )

                    else:

                        ok = self.exec.short(
                            proposal,
                            qty,
                            ctx["regime"],
                        )

                    if ok:

                        self.db.log(
                            "INFO",
                            "Selected paper trade: "
                            f"{proposal['symbol']} "
                            f"x{qty} "
                            f"strategy="
                            f"{proposal['strategy']}",
                        )

        # --------------------------------------------------
        # POST-TRADE POSITION PROTECTION
        # --------------------------------------------------

        self.positions.manage()

        # --------------------------------------------------
        # ACCOUNT SNAPSHOT
        # --------------------------------------------------

        self.snapshot()

    # ======================================================
    # ACCOUNT SNAPSHOT
    # ======================================================

    def snapshot(self):

        account = self.db.account()

        positions = self.db.positions()

        metrics = portfolio_metrics(
            account,
            positions,
            self.cfg[
                "execution"
            ].get(
                "short_margin_pct",
                0.25,
            ),
        )

        peak = max(
            float(
                account.get(
                    "peak_value",
                    0,
                )
                or 0
            ),
            metrics["equity"],
        )

        self.db.update_account(
            account["cash"],
            peak,
        )

        self.db.add_equity(
            metrics["equity"],
            (
                metrics["equity"]
                - account["starting_capital"]
            ),
        )

    # ======================================================
    # 24/7 ENGINE LOOP
    # ======================================================

    def run_forever(self):

        decision_interval = max(
            60,
            int(
                self.cfg[
                    "market"
                ][
                    "decision_interval_minutes"
                ]
                * 60
            ),
        )

        protection_interval = max(
            10,
            int(
                self.cfg[
                    "market"
                ].get(
                    "protection_interval_seconds",
                    30,
                )
            ),
        )

        next_decision = time.time()

        while True:

            now = time.time()

            # --------------------------------------------------
            # FULL AI DECISION CYCLE
            # --------------------------------------------------

            if now >= next_decision:

                try:

                    self.cycle()

                except Exception as exc:

                    self.db.log(
                        "ERROR",
                        repr(exc),
                    )

                next_decision = (
                    int(time.time())
                    // decision_interval
                    + 1
                ) * decision_interval

            # --------------------------------------------------
            # FAST POSITION PROTECTION LOOP
            # --------------------------------------------------

            else:

                try:

                    if self.db.positions():

                        self.positions.manage()

                except Exception as exc:

                    self.db.log(
                        "ERROR",
                        "Protection loop: "
                        f"{exc!r}",
                    )

            sleep_for = min(
                protection_interval,
                max(
                    1,
                    next_decision
                    - time.time(),
                ),
            )

            time.sleep(
                sleep_for
            )


if __name__ == "__main__":

    engine = TradingEngine()

    engine.run_forever()