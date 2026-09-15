from .backtest import Backtester

def run(df,train_bars=300,test_bars=100,step=100):
    """Strict chronological walk-forward evaluation. Training is a reserved past window; no test bar leaks backward."""
    results=[]; start=train_bars
    while start<len(df):
        train=df.iloc[start-train_bars:start]
        test=df.iloc[start:min(start+test_bars,len(df))]
        if len(train)<30 or len(test)<30: break
        # Baseline framework: strategy parameters are fixed, so training is audited but not optimized.
        bt=Backtester(); r=bt.run(test); r['train_start']=str(train.index[0]); r['train_end']=str(train.index[-1]); r['test_start']=str(test.index[0]); r['test_end']=str(test.index[-1]); results.append(r)
        start+=step
    return results
