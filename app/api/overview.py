"""
Overview & State API Blueprint
Provides primary portfolio metrics, execution history, and state synchronization.
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path
from flask import Blueprint, jsonify, render_template, request, current_app

from ..accounting import portfolio_metrics
from ..market_hours import market_phase, now_ist, holiday_name, market_open, IST
from ..news_archive import NewsArchive
from .auth import is_authorized

overview_bp = Blueprint("overview", __name__)


def _holding_minutes(opened_at):
    if not opened_at:
        return 0
    try:
        opened = datetime.fromisoformat(str(opened_at))
        if opened.tzinfo is None:
            opened = opened.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - opened).total_seconds() / 60))
    except Exception:
        return 0


def _enrich_trade(t):
    """Enriches trade records with human-readable IST entry and exit timestamps, direction, and P&L %."""
    if not t:
        return t
    trade = dict(t)
    entry = float(trade.get("entry_price", 0) or 0)
    exit_price = float(trade.get("exit_price", 0) or 0)
    qty = float(trade.get("qty", 1) or 1)
    side = str(trade.get("side", "LONG")).upper()
    trade["direction"] = "🟢 LONG" if side == "LONG" else "🔴 SHORT"

    if exit_price > 0 and entry > 0:
        pct = ((exit_price - entry) / entry) * 100 if side == "LONG" else ((entry - exit_price) / entry) * 100
        trade["pnl_pct"] = round(pct, 2)
    elif "pnl" in trade and entry > 0 and qty > 0:
        trade["pnl_pct"] = round((trade["pnl"] / (entry * qty)) * 100, 2)

    try:
        raw_created = str(trade.get("created_at") or "")
        created_dt = datetime.fromisoformat(raw_created.replace("Z", "+00:00")).astimezone(IST)
        exit_time_str = created_dt.strftime("%I:%M %p")
        exit_date_str = created_dt.strftime("%d %b %Y")
        trade["exit_time_ist"] = f"{exit_date_str}, {exit_time_str}"
        trade["exit_time"] = exit_time_str
        trade["exit_date"] = created_dt.strftime("%Y-%m-%d")

        holding_sec = float(trade.get("holding_seconds") or 0.0)
        entry_dt = created_dt - timedelta(seconds=holding_sec)
        entry_time_str = entry_dt.strftime("%I:%M %p")
        entry_date_str = entry_dt.strftime("%d %b %Y")
        trade["entry_time_ist"] = f"{entry_date_str}, {entry_time_str}"
        trade["entry_time"] = entry_time_str
        trade["entry_date"] = entry_dt.strftime("%Y-%m-%d")

        if trade["entry_date"] == trade["exit_date"]:
            trade["timing_display"] = f"{created_dt.strftime('%d %b')} · {entry_time_str} → {exit_time_str}"
        else:
            trade["timing_display"] = f"{entry_dt.strftime('%d %b')} {entry_time_str} → {created_dt.strftime('%d %b')} {exit_time_str}"
    except Exception:
        trade["exit_time_ist"] = str(trade.get("created_at", ""))
        trade["entry_time_ist"] = ""
        trade["timing_display"] = ""
    return trade


@overview_bp.route("/", methods=["GET"])
def home():
    return render_template("base.html")


@overview_bp.route("/health", methods=["GET"])
def health():
    """BUG-031: Expose engine liveness, cycle heartbeat, and trading readiness."""
    db = current_app.config.get("DB")
    try:
        account = db.account() if db else None
        last_cycle = db.get_last_cycle() if (db and hasattr(db, "get_last_cycle")) else None
        exceptions = db.get_exception_counts() if (db and hasattr(db, "get_exception_counts")) else {}
        data_ok = getattr(db, "_data_ok", True) if db else True
        auto_trading = db.is_auto_trading_enabled() if db else False
        is_ready = bool(account and data_ok and auto_trading)

        return jsonify({
            "version": "7.1",
            "status": "ok" if account else "degraded",
            "ready": is_ready,
            "paper_only": True,
            "database": "ok" if account else "uninitialized",
            "last_cycle_at": last_cycle,
            "data_ok": data_ok,
            "auto_trading": auto_trading,
            "exceptions": exceptions,
            "market_phase": market_phase(),
            "holiday": holiday_name()
        })
    except Exception as error:
        return jsonify({"status": "error", "paper_only": True, "error": repr(error)}), 500


@overview_bp.route("/api/state", methods=["GET"])
def state():
    db = current_app.config["DB"]
    cfg = current_app.config.get("CFG", {})
    provider = current_app.config.get("PROVIDER")
    learning = current_app.config.get("LEARNING")
    news_archive = current_app.config.get("NEWS_ARCHIVE")

    account = db.account()
    if not account:
        return jsonify({"error": "Trading account is not initialized."}), 503

    short_margin = float(cfg.get("execution", {}).get("short_margin_pct", 0.25))
    positions = db.positions()
    raw_trades = db.trades(30)
    trades = [_enrich_trade(t) for t in raw_trades]
    metrics = portfolio_metrics(account, positions, short_margin)
    realized = db.realized_pnl_today() if hasattr(db, "realized_pnl_today") else db.total_realized_pnl()
    realized_all_time = db.total_realized_pnl()
    pnl = metrics["equity"] - account["starting_capital"]

    drawdown = 0.0
    if account["peak_value"]:
        drawdown = ((account["peak_value"] - metrics["equity"]) / account["peak_value"]) * 100

    for position in positions:
        position["holding_minutes"] = _holding_minutes(position.get("opened_at"))
        qty = float(position.get("qty", 1) or 1)
        entry = float(position.get("entry_price", 0) or 0)
        curr = float(position.get("current_price", entry) or entry)
        side = str(position.get("side", "LONG")).upper()
        p_type = str(position.get("product_type", "INTRADAY")).upper()
        if p_type == "FNO" or side in ("SHORT", "SELL"):
            pos_pnl = (entry - curr) * qty
        else:
            pos_pnl = (curr - entry) * qty
        pos_pnl_pct = ((pos_pnl / (entry * qty)) * 100) if (entry * qty) > 0 else 0.0
        position["pnl"] = round(pos_pnl, 2)
        position["pnl_pct"] = round(pos_pnl_pct, 2)
        position["market_value"] = round(curr * qty, 2)

    decisions = db.decisions(10)
    market = db.market()
    market["market_phase"] = market_phase()
    market["holiday"] = holiday_name()

    alloc = db.get_capital_allocation()
    positions_intra = [p for p in positions if str(p.get("product_type", "INTRADAY")).upper() == "INTRADAY"]
    positions_swing = [p for p in positions if str(p.get("product_type", "")).upper() == "SWING"]
    positions_fno = [p for p in positions if str(p.get("product_type", "")).upper() == "FNO"]

    today_raw = db.trades_today() if hasattr(db, "trades_today") else []
    trades_today = [_enrich_trade(t) for t in today_raw]
    trades_intra_raw = db.trades_by_product("INTRADAY", 50) if hasattr(db, "trades_by_product") else [t for t in raw_trades if str(t.get("product_type", "INTRADAY")).upper() == "INTRADAY"]
    trades_intra = [_enrich_trade(t) for t in trades_intra_raw]

    trades_swing_raw = db.trades_by_product("SWING", 30) if hasattr(db, "trades_by_product") else [t for t in raw_trades if str(t.get("product_type", "")).upper() == "SWING"]
    trades_fno_raw = db.trades_by_product("FNO", 30) if hasattr(db, "trades_by_product") else [t for t in raw_trades if str(t.get("product_type", "")).upper() == "FNO"]
    trades_swing = [_enrich_trade(t) for t in trades_swing_raw]
    trades_fno = [_enrich_trade(t) for t in trades_fno_raw]

    from ..fno.index_chain import IndexChainManager
    fno_chain = IndexChainManager(provider)
    fno_expiry = fno_chain.get_next_expiry()
    fno_pcr = fno_chain.estimate_pcr("NIFTY")

    pending_all = db.pending_orders() if hasattr(db, "pending_orders") else []
    orders_fno = [o for o in pending_all if str(o.get("product_type", "")).upper() == "FNO"]

    # News Archive Intel
    recent_news_raw = news_archive.get_recent(limit=35) if news_archive else []
    news_stats = news_archive.get_news_summary_today() if news_archive else {"total": 0, "positive": 0, "negative": 0, "neutral": 0}
    enriched_news = []
    now_ts = datetime.now(timezone.utc)
    for n in recent_news_raw:
        pub_iso = n.get("published_at", "")
        time_ago_str = "Recently"
        ist_pub_str = ""
        if pub_iso:
            try:
                dt_val = datetime.fromisoformat(pub_iso.replace("Z", "+00:00"))
                ist_val = dt_val.astimezone(IST)
                ist_pub_str = ist_val.strftime("%I:%M %p IST")
                secs = max(0, (now_ts - dt_val).total_seconds())
                if secs < 60:
                    time_ago_str = "Just now"
                elif secs < 3600:
                    time_ago_str = f"{int(secs // 60)}m ago"
                elif secs < 86400:
                    time_ago_str = f"{int(secs // 3600)}h ago"
                else:
                    time_ago_str = f"{int(secs // 86400)}d ago"
            except Exception:
                pass

        sent = str(n.get("sentiment", "NEUTRAL")).upper()
        mat = str(n.get("materiality", "UNKNOWN")).upper()
        symbols = n.get("symbols", [])

        if sent == "POSITIVE":
            takeaway = "🟢 Growth catalyst / Positive earnings momentum"
        elif sent == "NEGATIVE":
            takeaway = "🔴 Risk factor flagged: AI Risk Guard blocks bad news stocks"
        else:
            takeaway = "⚪ Financial news & market intelligence update"

        enriched_news.append({
            "item_hash": n.get("item_hash"),
            "source": n.get("source"),
            "title": n.get("title"),
            "url": n.get("url"),
            "published_at": pub_iso,
            "published_ist": ist_pub_str,
            "time_ago": time_ago_str,
            "sentiment": sent,
            "materiality": mat,
            "symbols": symbols,
            "takeaway": takeaway
        })

    return jsonify({
        "version": "7.1",
        "paper_only": True,
        "auto_trading": db.is_auto_trading_enabled(),
        "total_pnl": pnl,
        "margin_used": metrics["reserved_margin"],
        "portfolio": metrics["equity"],
        "cash": metrics["cash"],
        "available_cash": metrics["available_cash"],
        "long_value": metrics["long_value"],
        "short_notional": metrics["short_notional"],
        "reserved_margin": metrics["reserved_margin"],
        "gross_exposure": metrics["gross_exposure"],
        "net_exposure": metrics["net_exposure"],
        "realized": round(realized, 2),
        "realized_today": round(realized, 2),
        "realized_all_time": round(realized_all_time, 2),
        "unrealized": (metrics["long_unrealized"] + metrics["short_unrealized"]),
        "daily_pnl": round(realized + (metrics["long_unrealized"] + metrics["short_unrealized"]), 2),
        "pnl": pnl,
        "return_pct": (pnl / account["starting_capital"] * 100),
        "target": account["target_capital"],
        "progress": (metrics["equity"] / account["target_capital"] * 100),
        "peak": account["peak_value"],
        "drawdown": drawdown,
        "capital_allocation": alloc,
        "positions": positions,
        "positions_intraday": positions_intra,
        "positions_swing": positions_swing,
        "positions_fno": positions_fno,
        "trades": trades,
        "trades_intraday": trades_intra,
        "trades_swing": trades_swing,
        "trades_fno": trades_fno,
        "decisions": decisions,
        "market": market,
        "learning": learning.recommendation() if learning else {"recommended_strategy": "Momentum", "confidence_multiplier": 1.0},
        "market_phase": market_phase(),
        "fno_expiry": fno_expiry,
        "fno_pcr": fno_pcr,
        "market_open": market_open(),
        "orders": db.orders(50),
        "pending_orders": pending_all,
        "orders_fno": orders_fno,
        "updated_at": now_ist().isoformat(),
        "equity_curve": db.equity(),
        "news": enriched_news,
        "news_stats": news_stats
    })


@overview_bp.route("/api/orders", methods=["GET"])
def get_orders():
    db = current_app.config["DB"]
    return jsonify({
        "orders": db.orders(50),
        "pending": db.pending_orders(),
        "market_open": market_open()
    })


@overview_bp.route("/api/runtime", methods=["GET"])
def runtime_state():
    cfg = current_app.config.get("CFG", {})
    provider = current_app.config.get("PROVIDER")
    from ..runtime import preflight
    return jsonify(preflight(cfg, provider))


@overview_bp.route("/api/learning", methods=["GET"])
def learning_state():
    learning = current_app.config.get("LEARNING")
    if learning:
        return jsonify(learning.recommendation())
    return jsonify({"recommended_strategy": "Momentum", "confidence_multiplier": 1.0})


@overview_bp.route("/api/capital/allocation", methods=["GET", "POST"])
def handle_capital_allocation():
    db = current_app.config["DB"]
    if request.method == "POST":
        if not is_authorized():
            return jsonify({"error": "Unauthorized"}), 401
        payload = request.get_json(silent=True) or {}
        intra = payload.get("intraday")
        sw = payload.get("swing")
        fno = payload.get("fno")
        updated = db.set_capital_allocation(intra, sw, fno)
        return jsonify({"status": "ok", "capital_allocation": updated})
    return jsonify(db.get_capital_allocation())
