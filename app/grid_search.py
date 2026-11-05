import itertools
import numpy as np
import pandas as pd
from .backtest import Backtester


def evaluate_parameter_grid(strategy_class, param_grid, datasets, starting_cash=100000.0, cost_cfg=None):
    """
    Evaluates a strategy across a parameter grid over multiple historical datasets.
    Returns performance metrics for each combination to analyze parameter sensitivity.
    """
    keys = list(param_grid.keys())
    combinations = list(itertools.product(*[param_grid[k] for k in keys]))
    results = []

    for combo in combinations:
        params = dict(zip(keys, combo))
        strat = strategy_class(**params)

        # Backtest this parameter instance across datasets
        bt = Backtester(starting_cash=starting_cash, cfg=cost_cfg)
        # Custom run injecting strategy's decide method
        prepared = {}
        for s, df in datasets.items():
            if df is not None and len(df) > 50: prepared[s] = df.copy()

        if not prepared: continue

        # Simulate execution
        positions = {}
        pending = {}
        idx = sorted(set().union(*(set(df.index) for df in prepared.values())))

        for ts in idx:
            # 1. Fill previous pending orders
            prices = {}
            for s, df in prepared.items():
                if ts not in df.index: continue
                row = df.loc[ts]
                prices[s] = float(row["Close"])
                if s in pending and s not in positions and len(positions) < bt.max_positions:
                    pside, patr, pstop, ptarg = pending.pop(s)
                    p = bt._open(s, row, pside, bt._mark(positions, prices), patr)
                    if p:
                        fill_px = p["entry"]
                        if patr and patr > 0:
                            stop_dist = max(patr * 1.5, fill_px * 0.005)
                            p["stop"] = round(fill_px - stop_dist, 2) if pside == "LONG" else round(fill_px + stop_dist, 2)
                            p["target"] = round(fill_px + stop_dist * 2.0, 2) if pside == "LONG" else round(fill_px - stop_dist * 2.0, 2)
                        else:
                            if pstop: p["stop"] = pstop
                            if ptarg: p["target"] = ptarg
                        p["mark"] = prices[s]
                        positions[s] = p

            # 2. Check stops/targets
            for s in list(positions):
                if ts not in prepared[s].index: continue
                row = prepared[s].loc[ts]
                p = positions[s]
                hit_stop = (float(row["Low"]) <= p["stop"]) if p["side"] == "LONG" else (float(row["High"]) >= p["stop"])
                hit_target = (float(row["High"]) >= p["target"]) if p["side"] == "LONG" else (float(row["Low"]) <= p["target"])
                p["mark"] = float(row["Close"])
                if hit_stop:
                    fill_px = min(p["stop"], float(row["Open"])) if p["side"] == "LONG" else max(p["stop"], float(row["Open"]))
                    bt._close(s, p, fill_px, "stop")
                    positions.pop(s)
                elif hit_target:
                    fill_px = max(p["target"], float(row["Open"])) if p["side"] == "LONG" else min(p["target"], float(row["Open"]))
                    bt._close(s, p, fill_px, "target")
                    positions.pop(s)

            # 3. Generate signals using the strategy instance
            for s, df in prepared.items():
                if ts not in df.index or s in positions or s in pending: continue
                i = df.index.get_loc(ts)
                if i + 1 >= len(df): continue
                sig = strat.decide(s, df.iloc[:i+1])
                if sig:
                    pending[s] = (sig["side"], float(sig["atr"]), sig.get("stop_loss"), sig.get("target"))

            if prices: bt.equity.append(bt._mark(positions, prices))

        for s, p in list(positions.items()):
            bt._close(s, p, float(prepared[s].iloc[-1]["Close"]), "end")

        res = bt.result()
        row_dict = dict(params)
        row_dict["return_pct"] = res["return_pct"]
        row_dict["trades"] = res["trades"]
        row_dict["win_rate"] = res["win_rate"]
        row_dict["max_drawdown_pct"] = res["max_drawdown_pct"]
        row_dict["profit_factor"] = res.get("profit_factor") or 0.0
        results.append(row_dict)

    return pd.DataFrame(results)


def detect_parameter_plateau(grid_df, metric="return_pct", max_cv=0.35):
    """
    Checks whether top-performing parameters form a robust plateau
    (low coefficient of variation across adjacent top candidates)
    rather than an overfitted spiky single-point peak.
    """
    if grid_df.empty or len(grid_df) < 3:
        return {"is_plateau": False, "reason": "Insufficient parameter iterations"}

    sorted_df = grid_df.sort_values(by=metric, ascending=False)
    # Analyze the top 25% parameter neighborhood
    top_k = max(2, int(len(sorted_df) * 0.25))
    top_slice = sorted_df.iloc[:top_k][metric].values

    mean_val = float(np.mean(top_slice))
    std_val = float(np.std(top_slice))
    cv = (std_val / abs(mean_val)) if abs(mean_val) > 1e-6 else 1.0

    is_plateau = (cv <= max_cv) and (mean_val > 0)
    return {
        "is_plateau": bool(is_plateau),
        "top_mean": round(mean_val, 2),
        "coefficient_of_variation": round(float(cv), 3),
        "best_params": dict(sorted_df.iloc[0].drop(["return_pct", "trades", "win_rate", "max_drawdown_pct", "profit_factor"], errors="ignore"))
    }


def evaluate_acceptance(strategy_name, perf, baseline_perf, min_trades=50, require_plateau=True):
    """
    Acceptance gate:
    A strategy is accepted only if it beats all baselines net of costs out-of-sample,
    maintains sufficient trade frequency, and displays stable parameter neighborhoods.
    """
    reasons = []
    strat_ret = perf.get("return_pct", 0.0)
    strat_trades = perf.get("trades", 0)

    # 1. Trade count check
    if strat_trades < min_trades:
        reasons.append(f"Insufficient trade sample: {strat_trades} < {min_trades}")

    # 2. Net return vs Baselines
    bnh_ret = baseline_perf.get("bnh_return_pct", 0.0)
    eq_ret = baseline_perf.get("eq_weight_return_pct", 0.0)
    if strat_ret <= bnh_ret:
        reasons.append(f"Failed to beat Buy & Hold baseline ({strat_ret:.2f}% <= {bnh_ret:.2f}%)")
    if strat_ret <= eq_ret:
        reasons.append(f"Failed to beat Equal-Weight baseline ({strat_ret:.2f}% <= {eq_ret:.2f}%)")

    # 3. Parameter plateau check
    if require_plateau and not perf.get("is_plateau", False):
        reasons.append("Failed parameter stability (spiky peak, not a robust plateau)")

    # 4. Maximum Drawdown check
    strat_dd = perf.get("max_drawdown_pct")
    base_dd = baseline_perf.get("max_drawdown_pct")
    if strat_dd is not None and base_dd is not None and strat_dd > base_dd * 1.5:
        reasons.append(f"Excessive drawdown: {strat_dd:.1f}% exceeds 1.5x baseline {base_dd:.1f}%")

    # 5. Random baseline comparison
    rand_exp = baseline_perf.get("random_expectancy")
    if rand_exp is not None and strat_ret <= rand_exp:
        reasons.append(f"Failed to beat random entry baseline ({strat_ret:.2f}% <= {rand_exp:.2f}%)")

    is_accepted = len(reasons) == 0
    return {
        "strategy": strategy_name,
        "status": "ACCEPTED" if is_accepted else "REJECTED",
        "return_pct": strat_ret,
        "trades": strat_trades,
        "rejections": reasons
    }
