import numpy as np


class ChampionChallengerManager:
    """
    Champion/Challenger Model Governance.
    Runs a Challenger model in parallel shadow paper trading alongside the Champion.
    Promotes the Challenger only if it statistically outperforms the Champion
    over a defined evaluation window net of costs.
    """
    def __init__(self, champion_model=None, challenger_model=None, min_evaluation_trades=20):
        self.champion = champion_model
        self.challenger = challenger_model
        self.min_trades = int(min_evaluation_trades)
        self.history = []  # list of {"champ_ret": float, "chall_ret": float}
        self.promotions = []

    def set_challenger(self, model):
        self.challenger = model
        self.history = []

    def record_decision_outcomes(self, features, realized_return, cost_pct=0.0012):
        if self.champion is None or self.challenger is None:
            return

        champ_dec = self.champion.predict_decision(features)
        chall_dec = self.challenger.predict_decision(features)

        # Net return if taken, 0.0 if skipped
        champ_net = (champ_dec["size_multiplier"] * (realized_return - cost_pct)) if champ_dec["take"] else 0.0
        chall_net = (chall_dec["size_multiplier"] * (realized_return - cost_pct)) if chall_dec["take"] else 0.0

        self.history.append({
            "champ_pnl": champ_net,
            "chall_pnl": chall_net
        })

    def evaluate_promotion(self):
        n = len(self.history)
        if n < self.min_trades:
            return {
                "promoted": False,
                "reason": f"Insufficient shadow evaluation sample ({n}/{self.min_trades} trades)",
                "trades": n
            }

        champ_pnls = np.array([x["champ_pnl"] for x in self.history])
        chall_pnls = np.array([x["chall_pnl"] for x in self.history])

        champ_exp = float(np.mean(champ_pnls))
        chall_exp = float(np.mean(chall_pnls))

        champ_std = float(np.std(champ_pnls)) or 1e-6
        chall_std = float(np.std(chall_pnls)) or 1e-6
        champ_sharpe = float((champ_exp / champ_std) * np.sqrt(252))
        chall_sharpe = float((chall_exp / chall_std) * np.sqrt(252))

        # Promotion rule: Challenger must deliver strictly higher expectancy and non-degraded Sharpe
        should_promote = (chall_exp > champ_exp) and (chall_sharpe >= champ_sharpe)

        if should_promote:
            old_champ = self.champion
            self.champion = self.challenger
            self.challenger = None
            self.promotions.append({
                "trades_evaluated": n,
                "champ_expectancy": round(champ_exp, 5),
                "chall_expectancy": round(chall_exp, 5),
                "chall_sharpe": round(chall_sharpe, 2)
            })
            self.history = []
            return {
                "promoted": True,
                "reason": "Challenger outperformed Champion across evaluation window",
                "old_expectancy": round(champ_exp, 5),
                "new_expectancy": round(chall_exp, 5)
            }

        return {
            "promoted": False,
            "reason": f"Challenger failed to outperform (Challenger: {chall_exp:.5f} vs Champion: {champ_exp:.5f})",
            "trades": n
        }
