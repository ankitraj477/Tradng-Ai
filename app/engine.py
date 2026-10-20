import time

from .config import load_config
from .db import DB
from .market_hours import (
    market_open,
    market_phase,
    holiday_name,
    now_ist,
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
from .intraday.timing import IntradayTimingManager
from .ops.kill_switch import CentralKillSwitch


class TradingEngine:

    def __init__(self, live=False, cfg=None, db=None, provider=None):
        self.cfg = cfg or load_config()

        # live=True enables live MARKET DATA only.
        # Execution remains paper-only.
        self.cfg["live_data"] = (
            live or self.cfg.get("live_data", False)
        )

        self.db = db or DB(
            self.cfg.get("database_path", "data/trader.db")
        )

        self.db.ensure_account(
            self.cfg.get("capital", {}).get("starting", 100000.0),
            self.cfg.get("capital", {}).get("target", 5000000.0),
        )



        # --------------------------------------------------
        # DATA PROVIDER
        # --------------------------------------------------

        if provider is not None:
            self.provider = provider
        elif self.cfg.get("live_data"):
            market_cfg = self.cfg.get("market", {})

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

        market_cfg = self.cfg.get("market", {})
        if not isinstance(market_cfg, dict):
            market_cfg = {}

        self.scanner = Scanner(
            market_cfg.get("max_candidates", 20),
            self.cfg.get("use_cpp_scanner", False),
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
            self.news,
            self.cfg,
        )

        self.ai = AITrader(
            self.learning,
            self.cfg,
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
            (self.cfg.get("risk") or {}).get(
                "max_sector_exposure_pct",
                0.40,
            ),
        )

        self.timing = IntradayTimingManager()

        self.kill_switch = CentralKillSwitch(
            self.db,
            self.exec,
            self.provider,
            self.cfg,
        )

        self.preflight = preflight(
            self.cfg,
            self.provider,
        )

        # BUG-006: Track whether we've done a catch-up close this session
        self._catch_up_done = False

        # Initialize the 3 decoupled trading desks
        from .intraday.runner import IntradayDeskRunner
        from .swing.runner import SwingDeskRunner
        from .fno.runner import FnoDeskRunner

        self.intraday_desk = IntradayDeskRunner(self.db, self.provider, self.cfg)
        self.swing_desk = SwingDeskRunner(self.db, self.provider, self.cfg)
        self.fno_desk = FnoDeskRunner(self.db, self.provider, self.cfg)

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
    # DYNAMIC CONFIG HOT-RELOAD
    # ======================================================

    def reload_config(self, new_cfg=None):
        """
        Dynamically reload configuration from disk on every cycle or from passed new_cfg.
        Allows tweaking risk caps, stop loss %, targets, and parameters without restarting.
        """
        try:
            live = self.cfg.get("live_data", False)
            if new_cfg is None:
                new_cfg = load_config()
            else:
                new_cfg = dict(new_cfg)
            new_cfg["live_data"] = live or new_cfg.get("live_data", False)
            self.cfg = new_cfg
            if hasattr(self, "ai") and self.ai:
                self.ai.cfg = self.cfg
            if hasattr(self, "risk") and self.risk:
                self.risk.cfg = self.cfg
            if hasattr(self, "pm") and self.pm:
                self.pm.cfg = self.cfg
            if hasattr(self, "exec") and self.exec:
                self.exec.cfg = self.cfg
            if hasattr(self, "positions") and self.positions:
                self.positions.cfg = self.cfg
            if hasattr(self, "intraday_desk") and self.intraday_desk:
                self.intraday_desk.cfg = self.cfg
            if hasattr(self, "swing_desk") and self.swing_desk:
                self.swing_desk.cfg = self.cfg
            if hasattr(self, "fno_desk") and self.fno_desk:
                self.fno_desk.cfg = self.cfg
            if "capital" in new_cfg:
                self.db.ensure_account(
                    float(new_cfg["capital"].get("starting", 100000.0)),
                    float(new_cfg["capital"].get("target", 5000000.0))
                )


        except Exception as exc:
            self.db.log("WARN", f"Dynamic config reload failed: {exc!r}")

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

            market_cfg = self.cfg.get("market") or {}
            df = self.provider.history(
                "^NSEI",
                period=market_cfg.get(
                    "history_period",
                    "60d",
                ),
                interval="5m",
            )

            ok, msg = validate_history(
                df,
                market_cfg.get(
                    "data_max_age_seconds",
                    600,
                ),
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
        self.reload_config()

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

            # BUG-006: Catch-up close — close any positions that survived past EOD
            if not self._catch_up_done and self.db.positions():
                closed = self.positions.catch_up_close()
                if closed > 0:
                    self.db.log("WARN", f"CATCH-UP CLOSE: Closed {closed} position(s) that survived past market close.")
                self._catch_up_done = True

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

            # Trigger off-market swing AMO placement and F&O research
            try:
                self.swing_desk.run_cycle()
            except Exception as exc:
                self.db.log("ERROR", f"Swing desk off-market cycle: {exc!r}")

            try:
                self.fno_desk.run_cycle()
            except Exception as exc:
                self.db.log("ERROR", f"F&O desk off-market cycle: {exc!r}")

            self.snapshot()
            return

        # Reset catch-up flag when market is open
        if self.cfg["live_data"] and market_open():
            self._catch_up_done = False

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
        # CENTRAL EMERGENCY KILL-SWITCH
        # --------------------------------------------------

        tripped, kill_reason = self.kill_switch.is_tripped()
        if tripped:
            self.db.log(
                "ERROR",
                f"CENTRAL KILL-SWITCH ACTIVE: {kill_reason}. Trading halted.",
            )
            self.snapshot()
            return

        # --------------------------------------------------
        # SESSION TIMING & EOD SQUARE-OFF
        # --------------------------------------------------

        if self.cfg.get("live_data"):
            current_ist = now_ist()
            if self.timing.must_square_off(current_ist):
                self.positions.manage(current_ist)
                self.db.log(
                    "INFO",
                    f"EOD SQUARE-OFF ACTIVE: Time is {current_ist.strftime('%H:%M:%S')} IST; square-off enforced.",
                )
                self.snapshot()
                return

            if not self.timing.can_enter(current_ist):
                self.positions.manage(current_ist)
                phase = self.timing.get_phase(current_ist)
                self.db.log(
                    "INFO",
                    f"SESSION TIMING GATE: Entry blocked during phase {phase} ({current_ist.strftime('%H:%M:%S')} IST).",
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
        self.positions.manage(now_ist() if self.cfg.get("live_data") else None)

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
                    proposal,
                    size_multiplier=ctx.get("size_multiplier", 1.0),
                )

                # BUG-009: Pass regime context to risk gate
                decision = self.risk.approve(
                    proposal,
                    qty,
                    regime_ctx=ctx,
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
            if not self.db.is_auto_trading_enabled():
                self.db.log(
                    "INFO",
                    "Auto-trading PAUSED. Background analysis and news monitoring active; order execution suspended.",
                )
            else:
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

                for chosen in ranked:
                    proposal, qty = next(
                        (
                            item
                            for item in proposals
                            if item[0]["symbol"]
                            == chosen["symbol"]
                        ),
                        (None, 0),
                    )
                    if not proposal or qty <= 0:
                        continue
                    ok = self.exec.buy(proposal, qty, ctx["regime"]) if proposal["action"] == "BUY" else self.exec.short(proposal, qty, ctx["regime"])
                    if ok:
                        self.db.log(
                            "INFO",
                            "Selected paper trade: "
                            f"{proposal['symbol']} "
                            f"x{qty} "
                            f"strategy="
                            f"{proposal['strategy']}",
                        )
                        break

        # --------------------------------------------------
        # POST-TRADE POSITION PROTECTION
        # --------------------------------------------------

        self.positions.manage()

        # Trigger all 3 decoupled desks in the unified cycle
        try:
            self.intraday_desk.run_cycle()
        except Exception as exc:
            self.db.log("ERROR", f"Intraday desk cycle: {exc!r}")

        try:
            self.swing_desk.run_cycle()
        except Exception as exc:
            self.db.log("ERROR", f"Swing desk cycle: {exc!r}")

        try:
            self.fno_desk.run_cycle()
        except Exception as exc:
            self.db.log("ERROR", f"F&O desk cycle: {exc!r}")

        # --------------------------------------------------
        # ACCOUNT SNAPSHOT
        # --------------------------------------------------

        self.snapshot()

        # BUG-031: Record heartbeat
        self.db.set_last_cycle()

    # ======================================================
    # ACCOUNT SNAPSHOT
    # ======================================================

    def snapshot(self):

        account = self.db.account()

        positions = self.db.positions()

        metrics = portfolio_metrics(
            account,
            positions,
            (self.cfg.get("execution") or {}).get(
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

        next_decision = time.time()

        while True:

            decision_interval = max(
                30,
                int(
                    self.cfg[
                        "market"
                    ].get(
                        "decision_interval_minutes",
                        1,
                    )
                    * 60
                ),
            )

            protection_interval = max(
                1,
                int(
                    self.cfg[
                        "market"
                    ].get(
                        "protection_interval_seconds",
                        5,
                    )
                ),
            )

            now = time.time()

            # --------------------------------------------------
            # FULL AI DECISION CYCLE
            # --------------------------------------------------

            if now >= next_decision:

                try:

                    self.cycle()

                except Exception as exc:
                    # BUG-029: Count cycle exceptions
                    self.db.count_exception("scanner")
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
                        if not self.cfg["live_data"] or market_open():
                            self.positions.manage(now_ist() if self.cfg.get("live_data") else None)
                            self.swing_desk.position_manager.manage()
                            self.fno_desk.position_manager.manage()

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