from app.db import DB
from app.learning import LearningEngine
from app.ai_trader import AITrader

def seed_trade(db, strategy, regime, pnl):
    with db.conn() as c:
        c.execute("""INSERT INTO trades(symbol,action,side,entry_price,exit_price,qty,capital,pnl,strategy,confidence,regime,created_at)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,datetime('now'))""",
                  ('X','SELL','LONG',10,10,1,10,pnl,strategy,80,regime))

def test_learning_waits_for_minimum_sample():
    db=DB(':memory:')
    for i in range(19): seed_trade(db,'Momentum','Strong bullish trend',1)
    le=LearningEngine(db,{'learning':{'min_trades':20}})
    assert le.weights()['Momentum']==1.0

def test_learning_is_bounded_after_sample():
    db=DB(':memory:')
    for i in range(20): seed_trade(db,'Momentum','Strong bullish trend',1)
    le=LearningEngine(db,{'learning':{'min_trades':20,'min_weight':.5,'max_weight':1.5}})
    assert .5 <= le.weights()['Momentum'] <= 1.5
    assert .5 <= le.weight_for('Momentum','Strong bullish trend') <= 1.5

def test_ai_exposes_learned_weight_without_changing_risk_policy():
    db=DB(':memory:')
    for i in range(20): seed_trade(db,'Momentum','Strong bullish trend',1)
    le=LearningEngine(db,{'learning':{'min_trades':20}})
    c={'symbol':'TEST','price':100,'score':80,'rsi':65,'atr':2,'rel_volume':1.5,'ret_5':.02,'ret_20':.05,'volatility':.1,'news_bias':0}
    p=AITrader(le).propose(c,'Strong bullish trend','Bullish')
    assert 'learned weight=' in p['reason']
    assert p['risk_reward'] >= 1.5
