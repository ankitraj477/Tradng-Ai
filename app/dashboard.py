from flask import Flask, jsonify, render_template_string
from .db import DB

HTML=r"""
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>AI Indian Paper Trader</title>
<style>
body{font-family:Arial;background:#0d1117;color:#e6edf3;margin:0}main{max-width:1250px;margin:auto;padding:24px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.card{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:16px}.big{font-size:24px;font-weight:bold;margin-top:6px}
section{margin-top:24px;background:#161b22;border:1px solid #30363d;border-radius:12px;padding:16px}
table{width:100%;border-collapse:collapse;overflow:auto}td,th{padding:8px;border-bottom:1px solid #30363d;text-align:left;font-size:13px}
.muted{color:#8b949e}.bar{height:12px;background:#30363d;border-radius:8px;overflow:hidden}.fill{height:100%;background:#58a6ff}
</style></head><body><main>
<h1>AI Indian Paper Trader</h1><div id="cards" class="grid"></div>
<section><h2>Target Progress</h2><div class="bar"><div id="fill" class="fill"></div></div><p id="progress"></p></section>
<section><h2>Current Holdings</h2><div id="positions"></div></section>
<section><h2>Last 10 Trades</h2><div id="trades"></div></section>
<section><h2>Market</h2><pre id="market"></pre></section>
<script>
async function load(){
 const d=await (await fetch('/api/state')).json();
 document.getElementById('cards').innerHTML=[
 ['Portfolio','₹'+d.portfolio.toFixed(2)],['Cash','₹'+d.cash.toFixed(2)],
 ['Total P&L','₹'+d.pnl.toFixed(2)],['Return',d.return_pct.toFixed(2)+'%'],
 ['Invested','₹'+d.invested.toFixed(2)],['Realized P&L','₹'+d.realized.toFixed(2)],
 ['Unrealized P&L','₹'+d.unrealized.toFixed(2)],['Drawdown',d.drawdown.toFixed(2)+'%']
 ].map(x=>`<div class="card"><div class="muted">${x[0]}</div><div class="big">${x[1]}</div></div>`).join('');
 document.getElementById('fill').style.width=Math.min(100,d.progress)+'%';
 document.getElementById('progress').textContent=`₹${d.portfolio.toFixed(2)} / ₹${d.target.toFixed(0)} — ${d.progress.toFixed(2)}%`;
 document.getElementById('positions').innerHTML=table(d.positions,['symbol','side','qty','entry_price','current_price','stop_loss','target','confidence']);
 document.getElementById('trades').innerHTML=table(d.trades,['symbol','action','qty','entry_price','exit_price','pnl','pnl_pct','holding_seconds','strategy','exit_reason']);
 document.getElementById('market').textContent=JSON.stringify(d.market,null,2);
}
function table(rows,cols){if(!rows.length)return '<p class="muted">None</p>';return '<div style="overflow:auto"><table><tr>'+cols.map(c=>`<th>${c}</th>`).join('')+'</tr>'+rows.map(r=>'<tr>'+cols.map(c=>`<td>${r[c]??''}</td>`).join('')+'</tr>').join('')+'</table></div>'}
load();setInterval(load,5000);
</script></main></body></html>
"""
def create_app(db):
    app=Flask(__name__)
    @app.get("/")
    def home(): return render_template_string(HTML)
    @app.get("/health")
    def health(): return jsonify({"status":"ok","paper_only":True})
    @app.get("/api/state")
    def state():
        a=db.account(); ps=db.positions(); trades=db.trades(10)
        invested=sum(p["qty"]*p["current_price"] for p in ps)
        unrealized=sum((p["current_price"]-p["entry_price"])*p["qty"] for p in ps)
        realized=sum((t["pnl"] or 0) for t in db.trades(100000))
        value=a["cash"]+invested; pnl=value-a["starting_capital"]
        draw=(a["peak_value"]-value)/a["peak_value"]*100 if a["peak_value"] else 0
        return jsonify({"portfolio":value,"cash":a["cash"],"invested":invested,
                        "realized":realized,"unrealized":unrealized,"pnl":pnl,
                        "return_pct":pnl/a["starting_capital"]*100,
                        "target":a["target_capital"],"progress":value/a["target_capital"]*100,
                        "peak":a["peak_value"],"drawdown":draw,
                        "positions":ps,"trades":trades,"market":db.market()})
    return app
