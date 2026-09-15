import sqlite3
from pathlib import Path
from datetime import datetime, timezone
SCHEMA=open(Path(__file__).with_name("schema.sql"),encoding="utf-8").read() if Path(__file__).with_name("schema.sql").exists() else ""
def now(): return datetime.now(timezone.utc).isoformat()
class DB:
    def __init__(self,path):
        Path(path).parent.mkdir(parents=True,exist_ok=True); self.path=path
        self._conn=None
        if path==":memory:":
            self._conn=sqlite3.connect(":memory:", check_same_thread=False)
            self._conn.row_factory=sqlite3.Row
        self.init()
    def conn(self):
        if self._conn is not None:
            return self._conn
        c=sqlite3.connect(self.path); c.row_factory=sqlite3.Row; return c
    def init(self):
        from .schema import SCHEMA
        with self.conn() as c:c.executescript(SCHEMA)
    def log(self,level,message):
        with self.conn() as c:c.execute("INSERT INTO events(level,message,created_at) VALUES(?,?,?)",(level,message,now()))
    def account(self):
        with self.conn() as c:
            r=c.execute("SELECT * FROM account WHERE id=1").fetchone(); return dict(r) if r else None
    def ensure_account(self,starting,target):
        if not self.account():
            with self.conn() as c:c.execute("INSERT INTO account VALUES(1,?,?,?,?,?)",(starting,starting,target,starting,now()))
    def positions(self):
        with self.conn() as c:return [dict(r) for r in c.execute("SELECT * FROM positions ORDER BY opened_at")]
    def trades(self,limit=10):
        with self.conn() as c:return [dict(r) for r in c.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?",(limit,))]
    def all_trades(self):
        with self.conn() as c:return [dict(r) for r in c.execute("SELECT * FROM trades ORDER BY id")]
    def update_account(self,cash,peak):
        with self.conn() as c:c.execute("UPDATE account SET cash=?,peak_value=?,updated_at=? WHERE id=1",(cash,peak,now()))
    def set_market(self,regime,sentiment,nifty,data_ok):
        with self.conn() as c:c.execute("""INSERT INTO market_state(id,regime,global_sentiment,nifty_condition,last_update,data_ok)
        VALUES(1,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET regime=excluded.regime,global_sentiment=excluded.global_sentiment,
        nifty_condition=excluded.nifty_condition,last_update=excluded.last_update,data_ok=excluded.data_ok""",(regime,sentiment,nifty,now(),int(data_ok)))
    def market(self):
        with self.conn() as c:
            r=c.execute("SELECT * FROM market_state WHERE id=1").fetchone();return dict(r) if r else {}
    def add_decision(self,d):
        with self.conn() as c:c.execute("""INSERT INTO decisions(symbol,action,confidence,strategy,reason,risk_decision,created_at)
        VALUES(?,?,?,?,?,?,?)""",(d["symbol"],d["action"],d["confidence"],d["strategy"],d["reason"],d["risk_decision"],now()))
    def add_equity(self,value,pnl):
        with self.conn() as c:c.execute("INSERT INTO equity_curve(value,pnl,created_at) VALUES(?,?,?)",(value,pnl,now()))
    def equity(self):
        with self.conn() as c:return [dict(r) for r in c.execute("SELECT * FROM equity_curve ORDER BY id")]
