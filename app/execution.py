from datetime import datetime, timezone
from .exchange_rules import round_to_tick, validate_order_microstructure
from .bracket_orders import BracketOrderManager

class PaperExecution:
    def __init__(self, db, cfg):
        self.db = db
        self.cfg = cfg
        self.bracket_manager = BracketOrderManager(self.db)

    def _slip(self, price, side):
        b = float(self.cfg.get('execution', {}).get('slippage_bps', 0)) / 10000
        if side == 'BUY':
            return round_to_tick(price * (1 + b))
        return round_to_tick(price * (1 - b))

    def buy(self, p, qty, regime):
        if qty <= 0 or any(x['symbol'] == p['symbol'] for x in self.db.positions()):
            return False
        fill = self._slip(p['price'], 'BUY')
        val = validate_order_microstructure(
            p['symbol'], 'BUY', fill,
            stop_loss=p.get('stop_loss'),
            target=p.get('target'),
            prev_close=p.get('prev_close')
        )
        if not val['ok']:
            self.db.log('WARN', f"ORDER REJECTED by exchange rules: {val['reason']}")
            return False

        value = fill * qty
        cost = self.cost(value, 'BUY', 'INTRADAY')
        sl = round_to_tick(p['stop_loss']) if p.get('stop_loss') is not None else None
        tp = round_to_tick(p['target']) if p.get('target') is not None else None

        with self.db.conn() as c:
            # BUG-027: Read cash inside transaction and use delta update
            row = c.execute("SELECT * FROM account WHERE id=1").fetchone()
            if not row:
                now_str = datetime.now(timezone.utc).isoformat()
                c.execute("INSERT OR IGNORE INTO account VALUES(1, 100000.0, 100000.0, 200000.0, 100000.0, ?)", (now_str,))
                row = c.execute("SELECT * FROM account WHERE id=1").fetchone()
            a = dict(row)
            margin_pct = self.cfg.get('execution', {}).get('short_margin_pct', 0.25)
            open_pos = [dict(r) for r in c.execute("SELECT * FROM positions").fetchall()]
            reserved = sum(float(x['entry_price']) * float(x['qty']) * margin_pct for x in open_pos if x['side'] == 'SHORT')
            avail = max(0.0, float(a['cash']) - reserved)
            if value + cost > avail:
                return False
            target_step = abs(float(tp) - fill) if tp is not None else 0.0
            prod_type = str(p.get('product_type', 'INTRADAY'))
            c.execute("""INSERT INTO positions(symbol,side,qty,entry_price,current_price,stop_loss,target,strategy,confidence,opened_at,sector,atr,entry_cost,target_step,product_type)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                p['symbol'], 'LONG', qty, fill, fill, sl, tp, p['strategy'], p['confidence'],
                datetime.now(timezone.utc).isoformat(), p.get('sector', 'Unknown'), p.get('atr'), cost, target_step, prod_type
            ))
            c.execute("UPDATE account SET cash=cash-?,updated_at=? WHERE id=1", (value + cost, datetime.now(timezone.utc).isoformat()))

        # Register active OCO bracket pair
        if sl is not None and tp is not None:
            self.bracket_manager.create_bracket(p['symbol'], 'LONG', qty, fill, sl, tp)

        self.db.log('INFO', f"PAPER BUY {p['symbol']} x{qty} @ {fill:.2f}")
        return True

    def short(self, p, qty, regime):
        if qty <= 0 or any(x['symbol'] == p['symbol'] for x in self.db.positions()):
            return False
        fill = self._slip(p['price'], 'SELL')
        val = validate_order_microstructure(
            p['symbol'], 'SELL', fill,
            stop_loss=p.get('stop_loss'),
            target=p.get('target'),
            prev_close=p.get('prev_close')
        )
        if not val['ok']:
            self.db.log('WARN', f"ORDER REJECTED by exchange rules: {val['reason']}")
            return False

        notional = fill * qty
        margin_pct = self.cfg['execution'].get('short_margin_pct', 0.25)
        margin = notional * margin_pct
        entry_cost = self.cost(notional, 'SELL', 'INTRADAY')
        sl = round_to_tick(p['stop_loss']) if p.get('stop_loss') is not None else None
        tp = round_to_tick(p['target']) if p.get('target') is not None else None

        with self.db.conn() as c:
            # BUG-027: Read cash inside transaction and use delta update
            row = c.execute("SELECT * FROM account WHERE id=1").fetchone()
            if not row:
                now_str = datetime.now(timezone.utc).isoformat()
                c.execute("INSERT OR IGNORE INTO account VALUES(1, 100000.0, 100000.0, 200000.0, 100000.0, ?)", (now_str,))
                row = c.execute("SELECT * FROM account WHERE id=1").fetchone()
            a = dict(row)
            open_pos = [dict(r) for r in c.execute("SELECT * FROM positions").fetchall()]
            reserved = sum(float(x['entry_price']) * float(x['qty']) * margin_pct for x in open_pos if x['side'] == 'SHORT')
            avail = max(0.0, float(a['cash']) - reserved)
            if margin + entry_cost > avail:
                return False
            target_step = abs(fill - float(tp)) if tp is not None else 0.0
            prod_type = str(p.get('product_type', 'INTRADAY'))
            c.execute("""INSERT INTO positions(symbol,side,qty,entry_price,current_price,stop_loss,target,strategy,confidence,opened_at,sector,atr,entry_cost,target_step,product_type)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                p['symbol'], 'SHORT', qty, fill, fill, sl, tp, p['strategy'], p['confidence'],
                datetime.now(timezone.utc).isoformat(), p.get('sector', 'Unknown'), p.get('atr'), entry_cost, target_step, prod_type
            ))
            # Only actual entry costs leave cash; margin is tracked via position.
            c.execute("UPDATE account SET cash=cash-?,updated_at=? WHERE id=1", (entry_cost, datetime.now(timezone.utc).isoformat()))

        # Register active OCO bracket pair
        if sl is not None and tp is not None:
            self.bracket_manager.create_bracket(p['symbol'], 'SHORT', qty, fill, sl, tp)

        self.db.log('INFO', f"PAPER SHORT {p['symbol']} x{qty} @ {fill:.2f} margin={margin:.2f}")
        return True

    def mark(self, quotes):
        with self.db.conn() as c:
            for q in quotes:
                c.execute("UPDATE positions SET current_price=? WHERE symbol=?", (round_to_tick(q['price']), q['symbol']))

    def close(self, symbol, price, reason, regime):
        with self.db.conn() as c:
            row = c.execute("SELECT * FROM positions WHERE symbol=?", (symbol,)).fetchone()
            if not row:
                return False
            p = dict(row)
            side = p['side']
            fill = self._slip(price, 'SELL' if side == 'LONG' else 'BUY')
            notional = abs(fill * p['qty'])
            if side == 'LONG':
                gross = (fill - p['entry_price']) * p['qty']
                released = fill * p['qty']
                entry_cap = p['entry_price'] * p['qty']
            else:
                gross = (p['entry_price'] - fill) * p['qty']
                released = gross
                entry_cap = p['entry_price'] * p['qty']
            entry_cost = float(p.get('entry_cost') or 0)
            exit_cost = self.cost(notional, 'SELL' if side == 'LONG' else 'BUY', 'INTRADAY')
            pnl = gross - exit_cost - entry_cost
            opened = datetime.fromisoformat(p['opened_at'])
            holding = (datetime.now(timezone.utc) - opened).total_seconds()
            pnl_pct = pnl / entry_cap * 100 if entry_cap else 0
            prod_type = str(p.get('product_type', 'INTRADAY'))
            c.execute("""INSERT INTO trades(symbol,action,side,entry_price,exit_price,qty,capital,stop_loss,target,holding_seconds,pnl,pnl_pct,strategy,confidence,regime,entry_reason,exit_reason,risk_decision,created_at,product_type)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                symbol, 'SELL' if side == 'LONG' else 'COVER', side, p['entry_price'], fill, p['qty'],
                entry_cap, p['stop_loss'], p['target'], holding, pnl, pnl_pct, p['strategy'],
                p['confidence'], regime, 'AI proposal', reason, 'APPROVED', datetime.now(timezone.utc).isoformat(), prod_type
            ))
            c.execute("DELETE FROM positions WHERE symbol=?", (symbol,))
            # BUG-027: Delta update for cash — all within single transaction
            c.execute("UPDATE account SET cash=cash+?,updated_at=? WHERE id=1", (released - exit_cost, datetime.now(timezone.utc).isoformat()))

        # Cancel active bracket legs for this position
        self.bracket_manager.cancel_bracket(symbol, reason=reason)

        self.db.log('INFO', f"PAPER {side} CLOSE {symbol} @ {fill:.2f} P&L={pnl:.2f}")
        return True

    def cost(self, value, action, segment='INTRADAY'):
        if not hasattr(self, '_cost_model'):
            from .costs import CostModel
            self._cost_model = CostModel(self.cfg)
        return self._cost_model.calculate(value, action, segment)

