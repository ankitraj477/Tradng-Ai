SCHEMA = """
CREATE TABLE IF NOT EXISTS account (
 id INTEGER PRIMARY KEY CHECK(id=1), cash REAL NOT NULL, starting_capital REAL NOT NULL,
 target_capital REAL NOT NULL, peak_value REAL NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS positions (
 symbol TEXT PRIMARY KEY, side TEXT NOT NULL, qty INTEGER NOT NULL, entry_price REAL NOT NULL,
 current_price REAL NOT NULL, stop_loss REAL, target REAL, strategy TEXT, confidence REAL,
 opened_at TEXT NOT NULL, sector TEXT, atr REAL);
CREATE TABLE IF NOT EXISTS trades (
 id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, action TEXT NOT NULL, side TEXT NOT NULL,
 entry_price REAL, exit_price REAL, qty INTEGER NOT NULL, capital REAL NOT NULL, stop_loss REAL, target REAL,
 holding_seconds REAL, pnl REAL, pnl_pct REAL, strategy TEXT, confidence REAL, regime TEXT,
 entry_reason TEXT, exit_reason TEXT, risk_decision TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS decisions (
 id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, action TEXT, confidence REAL, strategy TEXT,
 reason TEXT, risk_decision TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS market_state (
 id INTEGER PRIMARY KEY CHECK(id=1), regime TEXT, global_sentiment TEXT, nifty_condition TEXT,
 last_update TEXT, data_ok INTEGER);
CREATE TABLE IF NOT EXISTS equity_curve (
 id INTEGER PRIMARY KEY AUTOINCREMENT, value REAL NOT NULL, pnl REAL NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS stop_updates (
 id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, old_stop REAL,
 new_stop REAL NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, level TEXT, message TEXT, created_at TEXT NOT NULL);
"""
