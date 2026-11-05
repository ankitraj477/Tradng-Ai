import numpy as np
import pandas as pd
from .backtest import Backtester


def calculate_metrics(equity_curve, trades, starting_capital=100000.0, annualization_factor=252.0):
    """Calculates quantitative performance metrics strictly on daily return horizons."""
    eq = np.array(equity_curve, dtype=float) if len(equity_curve) > 1 else np.array([starting_capital, starting_capital])
    peak = np.maximum.accumulate(eq)
    drawdowns = (peak - eq) / np.where(peak > 0, peak, 1.0)
    max_dd_pct = float(np.max(drawdowns) * 100.0)

    daily_returns = np.diff(eq) / np.where(eq[:-1] > 0, eq[:-1], 1.0)
    mean_ret = float(np.mean(daily_returns)) if len(daily_returns) else 0.0
    std_ret = float(np.std(daily_returns)) if len(daily_returns) else 0.0

    sharpe = float((mean_ret / std_ret) * np.sqrt(annualization_factor)) if std_ret > 1e-9 else 0.0
    downside = daily_returns[daily_returns < 0]
    downside_std = float(np.std(downside)) if len(downside) else 0.0
    sortino = float((mean_ret / downside_std) * np.sqrt(annualization_factor)) if downside_std > 1e-9 else 0.0

    n_days = max(1, len(daily_returns))
    cagr = float(((eq[-1] / starting_capital) ** (annualization_factor / n_days) - 1.0) * 100.0) if eq[-1] > 0 else -100.0

    pnls = [t.get("pnl", 0.0) for t in trades]
    n_trades = len(pnls)
    expectancy = float(np.mean(pnls)) if n_trades else 0.0
    wins = [p for p in pnls if p > 0]
    win_rate = float(len(wins) / n_trades * 100.0) if n_trades else 0.0

    # 95% Bootstrap Confidence Interval on Win Rate
    ci_lower, ci_upper = (0.0, 0.0)
    if n_trades >= 10:
        rng = np.random.default_rng(42)
        boot_wins = [np.mean(rng.choice(pnls, size=n_trades, replace=True) > 0) * 100.0 for _ in range(500)]
        ci_lower = float(np.percentile(boot_wins, 2.5))
        ci_upper = float(np.percentile(boot_wins, 97.5))

    return {
        "cagr": round(cagr, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "expectancy_per_trade": round(expectancy, 2),
        "trades_count": n_trades,
        "win_rate": round(win_rate, 2),
        "win_rate_ci_95": (round(ci_lower, 2), round(ci_upper, 2)),
        "final_equity": round(float(eq[-1]), 2)
    }


def walk_forward_evaluate(datasets, train_bars=120, test_bars=40, purge_bars=5, embargo_bars=2, starting_capital=100000.0, cfg=None):
    """
    Rolling purged and embargoed walk-forward evaluation.
    Only evaluates out-of-sample test slices to prevent lookahead and data leakage.
    """
    valid = {s: df for s, df in datasets.items() if df is not None and len(df) >= (train_bars + test_bars)}
    if not valid:
        return {"error": "Insufficient history across datasets for walk-forward evaluation", "windows": []}

    all_dates = sorted(set().union(*(set(df.index) for df in valid.values())))
    total_bars = len(all_dates)
    step = test_bars
    windows = []
    combined_trades = []
    equity_progression = [starting_capital]

    current_start = 0
    while current_start + train_bars + purge_bars + test_bars <= total_bars:
        train_start = all_dates[current_start]
        train_end = all_dates[current_start + train_bars - 1]

        # Purge gap: skips `purge_bars` to avoid holding overlap
        test_start_idx = current_start + train_bars + purge_bars
        test_end_idx = min(total_bars - 1, test_start_idx + test_bars - 1)
        test_start = all_dates[test_start_idx]
        test_end = all_dates[test_end_idx]

        test_data = {}
        for s, df in valid.items():
            sub = df.loc[(df.index >= test_start) & (df.index <= test_end)]
            if len(sub) >= 10: test_data[s] = sub

        if test_data:
            bt = Backtester(starting_cash=equity_progression[-1], cfg=cfg)
            res = bt.run_portfolio(test_data)
            combined_trades.extend(res.get("trades_detail", []))
            equity_progression.extend(bt.equity[1:] if len(bt.equity) > 1 else [bt.cash])
            windows.append({
                "train_range": (str(train_start)[:10], str(train_end)[:10]),
                "test_range": (str(test_start)[:10], str(test_end)[:10]),
                "trades": res.get("trades", 0),
                "pnl": res.get("pnl", 0.0),
                "return_pct": res.get("return_pct", 0.0)
            })

        # Advance with embargo
        current_start += step + embargo_bars

    metrics = calculate_metrics(equity_progression, combined_trades, starting_capital=starting_capital)
    metrics["windows_tested"] = len(windows)
    metrics["window_summaries"] = windows
    return metrics
