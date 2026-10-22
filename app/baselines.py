import numpy as np
import pandas as pd
from .costs import CostModel


def buy_and_hold_baseline(df, starting_capital=100000.0, cost_model=None):
    """Computes buy-and-hold benchmark (e.g. NIFTY 50) net of costs."""
    if df is None or df.empty or len(df) < 2:
        return {"return_pct": 0.0, "cagr": 0.0, "max_drawdown_pct": 0.0, "equity": [starting_capital]}

    cm = cost_model or CostModel()
    start_px = float(df["Open"].iloc[0])
    end_px = float(df["Close"].iloc[-1])

    # Buy at first open, sell at last close
    shares = starting_capital / start_px
    entry_fee = cm.calculate(starting_capital, "BUY", "DELIVERY")
    exit_value = shares * end_px
    exit_fee = cm.calculate(exit_value, "SELL", "DELIVERY")

    final_capital = exit_value - entry_fee - exit_fee
    ret_pct = ((final_capital / starting_capital) - 1.0) * 100.0

    curve = (df["Close"] / start_px) * starting_capital
    peak = curve.cummax()
    dd = (peak - curve) / peak
    max_dd = float(dd.max() * 100.0) if len(dd) else 0.0

    delta = df.index[-1] - df.index[0]
    days = max(1, delta.days if hasattr(delta, 'days') else len(df))
    years = max(days / 365.25, 1/252)
    cagr = ((final_capital / starting_capital) ** (1.0 / years) - 1.0) * 100.0 if final_capital > 0 else -100.0

    return {
        "return_pct": float(ret_pct),
        "cagr": float(cagr),
        "max_drawdown_pct": float(max_dd),
        "final_capital": float(final_capital),
        "equity": curve.tolist()
    }


def equal_weight_baseline(datasets, starting_capital=100000.0, cost_model=None):
    """Computes equal-weight benchmark across an active constituent universe."""
    cm = cost_model or CostModel()
    valid = {s: df for s, df in datasets.items() if df is not None and not df.empty and "Close" in df.columns}
    if not valid:
        return {"return_pct": 0.0, "cagr": 0.0, "max_drawdown_pct": 0.0, "final_capital": starting_capital}

    closes = pd.DataFrame({s: df["Close"] for s, df in valid.items()}).dropna(how="all").ffill().bfill()
    daily_rets = closes.pct_change().mean(axis=1).fillna(0.0)
    curve = starting_capital * (1.0 + daily_rets).cumprod()

    peak = curve.cummax()
    dd = (peak - curve) / peak
    raw_final_cap = float(curve.iloc[-1]) if len(curve) else starting_capital
    entry_fee = cm.calculate(starting_capital, "BUY", "DELIVERY")
    exit_fee = cm.calculate(raw_final_cap, "SELL", "DELIVERY")
    final_cap = max(0.0, raw_final_cap - entry_fee - exit_fee)
    ret_pct = ((final_cap / starting_capital) - 1.0) * 100.0

    years = max(len(daily_rets) / 252.0, 1/252)
    cagr = ((final_cap / starting_capital) ** (1.0 / years) - 1.0) * 100.0 if final_cap > 0 else -100.0

    return {
        "return_pct": float(ret_pct),
        "cagr": float(cagr),
        "max_drawdown_pct": float(dd.max() * 100.0) if len(dd) else 0.0,
        "final_capital": float(final_cap)
    }


def random_entries_baseline(datasets, n_trades=100, holding_bars=5, starting_capital=100000.0, cost_model=None, seed=42):
    """Simulates random trades with matched holding duration to verify zero-edge expectancy after fees."""
    rng = np.random.default_rng(seed)
    cm = cost_model or CostModel()
    symbols = list(datasets.keys())
    if not symbols: return {"trades": 0, "expectancy": 0.0, "total_pnl": 0.0}

    trades = []
    trade_size = starting_capital * 0.10  # 10% sizing per trade

    for _ in range(n_trades):
        sym = rng.choice(symbols)
        df = datasets[sym]
        if len(df) <= holding_bars + 1: continue
        entry_idx = rng.integers(0, len(df) - holding_bars - 1)
        exit_idx = entry_idx + holding_bars

        entry_px = float(df["Open"].iloc[entry_idx + 1])
        exit_px = float(df["Open"].iloc[exit_idx + 1])
        side = "LONG" if rng.random() > 0.5 else "SHORT"

        shares = trade_size / entry_px
        notional = shares * entry_px
        exit_val = shares * exit_px
        entry_fee = cm.calculate(notional, "BUY" if side == "LONG" else "SELL", "INTRADAY")
        exit_fee = cm.calculate(exit_val, "SELL" if side == "LONG" else "BUY", "INTRADAY")

        gross = (exit_val - notional) if side == "LONG" else (notional - exit_val)
        net_pnl = gross - entry_fee - exit_fee
        trades.append(net_pnl)

    pnls = np.array(trades) if trades else np.array([0.0])
    return {
        "trades": len(trades),
        "total_pnl": float(pnls.sum()),
        "expectancy": float(pnls.mean()) if len(trades) else 0.0,
        "win_rate": float((pnls > 0).mean() * 100.0) if len(trades) else 0.0
    }
