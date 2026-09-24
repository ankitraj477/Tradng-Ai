from datetime import datetime, timezone
from flask import Flask, jsonify, render_template_string

from .accounting import portfolio_metrics
from .market_hours import market_phase, now_ist, holiday_name
from .learning import LearningEngine
from .runtime import preflight


HTML = r"""
<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width">
    <title>AI Indian Paper Trader — V10.1</title>

    <style>
        body {
            font-family: Arial, sans-serif;
            background: #0d1117;
            color: #e6edf3;
            margin: 0;
        }

        main {
            max-width: 1400px;
            margin: auto;
            padding: 20px;
        }

        .grid {
            display: grid;
            grid-template-columns:
                repeat(auto-fit, minmax(170px, 1fr));
            gap: 10px;
        }

        .card {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 14px;
        }

        .big {
            font-size: 22px;
            font-weight: 700;
            margin-top: 6px;
        }

        .muted {
            color: #8b949e;
            font-size: 12px;
        }

        section {
            margin-top: 18px;
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 15px;
        }

        h1 {
            margin-bottom: 4px;
        }

        h2 {
            margin-top: 0;
            font-size: 18px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
        }

        td,
        th {
            padding: 7px;
            border-bottom: 1px solid #30363d;
            text-align: left;
            font-size: 12px;
            white-space: nowrap;
        }

        .scroll {
            overflow: auto;
        }

        .bar {
            height: 12px;
            background: #30363d;
            border-radius: 8px;
            overflow: hidden;
        }

        .fill {
            height: 100%;
            background: #58a6ff;
            width: 0%;
        }

        .two {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 14px;
        }

        @media (max-width: 800px) {
            .two {
                grid-template-columns: 1fr;
            }
        }

        .error {
            color: #ff7b72;
        }
    </style>
</head>

<body>

<main>

    <h1>AI Indian Paper Trader — V10.1</h1>

    <div id="status" class="muted">
        Loading...
    </div>

    <div id="cards" class="grid"></div>

    <section>
        <h2>Target Progress</h2>

        <div class="bar">
            <div id="fill" class="fill"></div>
        </div>

        <p id="progress"></p>
    </section>

    <div class="two">

        <section>
            <h2>Current Holdings</h2>
            <div id="positions"></div>
        </section>

        <section>
            <h2>Last 10 Trades</h2>
            <div id="trades"></div>
        </section>

    </div>

    <div class="two">

        <section>
            <h2>Recent AI Decisions</h2>
            <div id="decisions"></div>
        </section>

        <section>
            <h2>Market / Risk State</h2>
            <pre id="market"></pre>
        </section>

    </div>

</main>

<script>

const money = value =>
    '₹' + Number(value || 0).toFixed(2);


async function loadDashboard() {

    try {

        const response = await fetch(
            '/api/state',
            { cache: 'no-store' }
        );

        if (!response.ok) {
            throw new Error(
                'HTTP ' + response.status
            );
        }

        const data = await response.json();


        document.getElementById(
            'status'
        ).textContent =
            `${data.market_phase} · ` +
            `${data.paper_only ? 'PAPER ONLY' : ''} · ` +
            `updated ${data.updated_at}`;


        const cards = [

            ['Portfolio', money(data.portfolio)],

            ['Cash', money(data.cash)],

            ['Available Cash',
             money(data.available_cash)],

            ['Total P&L',
             money(data.pnl)],

            ['Return',
             Number(data.return_pct || 0).toFixed(2) + '%'],

            ['Long Value',
             money(data.long_value)],

            ['Short Notional',
             money(data.short_notional)],

            ['Reserved Margin',
             money(data.reserved_margin)],

            ['Gross Exposure',
             money(data.gross_exposure)],

            ['Net Exposure',
             money(data.net_exposure)],

            ['Realized P&L',
             money(data.realized)],

            ['Unrealized P&L',
             money(data.unrealized)],

            ['Drawdown',
             Number(data.drawdown || 0).toFixed(2) + '%']

        ];


        document.getElementById(
            'cards'
        ).innerHTML = cards.map(
            item => `
                <div class="card">
                    <div class="muted">
                        ${escapeHtml(item[0])}
                    </div>

                    <div class="big">
                        ${escapeHtml(item[1])}
                    </div>
                </div>
            `
        ).join('');


        const progress = Math.max(
            0,
            Math.min(
                100,
                Number(data.progress || 0)
            )
        );


        document.getElementById(
            'fill'
        ).style.width = progress + '%';


        document.getElementById(
            'progress'
        ).textContent =
            `${money(data.portfolio)} / ` +
            `${money(data.target)} — ` +
            `${progress.toFixed(2)}%`;


        document.getElementById(
            'positions'
        ).innerHTML = table(
            data.positions || [],
            [
                'symbol',
                'side',
                'qty',
                'entry_price',
                'current_price',
                'stop_loss',
                'target',
                'confidence',
                'holding_minutes'
            ]
        );


        document.getElementById(
            'trades'
        ).innerHTML = table(
            data.trades || [],
            [
                'symbol',
                'action',
                'qty',
                'entry_price',
                'exit_price',
                'pnl',
                'pnl_pct',
                'holding_seconds',
                'strategy',
                'exit_reason'
            ]
        );


        document.getElementById(
            'decisions'
        ).innerHTML = table(
            data.decisions || [],
            [
                'symbol',
                'action',
                'confidence',
                'strategy',
                'risk_decision',
                'reason',
                'created_at'
            ]
        );


        document.getElementById(
            'market'
        ).textContent =
            JSON.stringify(
                data.market || {},
                null,
                2
            );


    } catch (error) {

        document.getElementById(
            'status'
        ).innerHTML =
            '<span class="error">' +
            'Dashboard error: ' +
            escapeHtml(error.message) +
            '</span>';
    }
}


function escapeHtml(value) {

    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}


function table(rows, columns) {

    if (!rows.length) {
        return '<p class="muted">None</p>';
    }


    const header = columns
        .map(
            column =>
                `<th>${escapeHtml(column)}</th>`
        )
        .join('');


    const body = rows
        .map(
            row =>
                '<tr>' +
                columns
                    .map(
                        column =>
                            `<td>${escapeHtml(
                                row[column]
                            )}</td>`
                    )
                    .join('') +
                '</tr>'
        )
        .join('');


    return `
        <div class="scroll">
            <table>
                <thead>
                    <tr>${header}</tr>
                </thead>

                <tbody>
                    ${body}
                </tbody>
            </table>
        </div>
    `;
}


loadDashboard();

setInterval(
    loadDashboard,
    5000
);

</script>

</body>
</html>
"""


def _holding_minutes(opened_at):

    try:

        opened = datetime.fromisoformat(
            opened_at
        )

        return round(
            (
                datetime.now(timezone.utc)
                - opened
            ).total_seconds() / 60,
            1
        )

    except Exception:

        return 0.0


def create_app(db, cfg=None, provider=None):

    cfg = cfg or {}

    flask_app = Flask(__name__)

    short_margin = (
        cfg
        .get("execution", {})
        .get("short_margin_pct", 0.25)
    )

    learning = LearningEngine(
        db,
        cfg
    )


    @flask_app.get("/")
    def home():

        return render_template_string(
            HTML
        )


    @flask_app.get("/health")
    def health():

        try:

            account = db.account()

            return jsonify({
                "status": "ok",
                "paper_only": True,
                "database":
                    "ok"
                    if account
                    else "missing",
                "market_phase":
                    market_phase(),
                "holiday":
                    holiday_name()
            })

        except Exception as error:

            return jsonify({
                "status": "error",
                "paper_only": True,
                "error": repr(error)
            }), 500


    @flask_app.get("/api/runtime")
    def runtime_state():

        return jsonify(
            preflight(
                cfg,
                provider
            )
        )


    @flask_app.get("/api/learning")
    def learning_state():

        return jsonify(
            learning.recommendation()
        )


    @flask_app.get("/api/state")
    def state():

        account = db.account()

        if not account:

            return jsonify({
                "error":
                    "Trading account is not initialized."
            }), 503


        positions = db.positions()

        trades = db.trades(10)

        metrics = portfolio_metrics(
            account,
            positions,
            short_margin
        )


        realized = sum(
            float(trade.get("pnl") or 0)
            for trade in db.all_trades()
        )


        pnl = (
            metrics["equity"]
            - account["starting_capital"]
        )


        drawdown = 0.0

        if account["peak_value"]:

            drawdown = (
                (
                    account["peak_value"]
                    - metrics["equity"]
                )
                / account["peak_value"]
            ) * 100


        for position in positions:

            position["holding_minutes"] = (
                _holding_minutes(
                    position["opened_at"]
                )
            )


        decisions = db.decisions(10)


        market = db.market()

        market["market_phase"] = (
            market_phase()
        )

        market["holiday"] = (
            holiday_name()
        )


        return jsonify({

            "paper_only": True,

            "portfolio":
                metrics["equity"],

            "cash":
                metrics["cash"],

            "available_cash":
                metrics["available_cash"],

            "long_value":
                metrics["long_value"],

            "short_notional":
                metrics["short_notional"],

            "reserved_margin":
                metrics["reserved_margin"],

            "gross_exposure":
                metrics["gross_exposure"],

            "net_exposure":
                metrics["net_exposure"],

            "realized":
                realized,

            "unrealized":
                (
                    metrics["long_unrealized"]
                    + metrics["short_unrealized"]
                ),

            "pnl":
                pnl,

            "return_pct":
                (
                    pnl
                    / account["starting_capital"]
                    * 100
                ),

            "target":
                account["target_capital"],

            "progress":
                (
                    metrics["equity"]
                    / account["target_capital"]
                    * 100
                ),

            "peak":
                account["peak_value"],

            "drawdown":
                drawdown,

            "positions":
                positions,

            "trades":
                trades,

            "decisions":
                decisions,

            "market":
                market,

            "learning":
                learning.recommendation(),

            "market_phase":
                market_phase(),

            "updated_at":
                now_ist().isoformat()
        })


    return flask_app


def _load_runtime():
    """
    Build the default dashboard application.

    This allows:

        python -m app.dashboard

    to start the Flask dashboard directly.
    """

    import json
    from pathlib import Path

    from .db import DB

    root = Path(__file__).resolve().parent.parent

    config_path = root / "config" / "default.json"

    with open(
        config_path,
        "r",
        encoding="utf-8"
    ) as file:
        cfg = json.load(file)

    # V10/V10.1 stores the database in the
    # project's data directory.
    data_dir = root / "data"
    data_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    database_path = data_dir / "trader.db"

    db = DB(
        str(database_path)
    )

    # Create the paper-trading account if it
    # does not already exist.
    db.ensure_account(
        cfg["capital"]["starting"],
        cfg["capital"]["target"]
    )

    return create_app(
        db=db,
        cfg=cfg
    )


app = _load_runtime()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )