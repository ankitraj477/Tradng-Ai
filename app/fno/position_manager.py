"""
F&O Position Manager.
Enforces the institutional 50% Profit-Taking Rule for theta decay,
stop-loss limits, and Thursday 15:15 IST expiry square-off.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
from .sr_levels import IndexSRCalculator

IST = ZoneInfo("Asia/Kolkata")


class FNOPositionManager:
    def __init__(self, db, execution, chain_manager=None, cfg=None):
        self.db = db
        self.execution = execution
        self.chain = chain_manager
        self.cfg = cfg or {}
        self.sr_calc = IndexSRCalculator(provider=getattr(chain_manager, "provider", None) if chain_manager else None)

    def manage(self, dt=None) -> int:
        """
        Evaluate and protect all open FNO positions every 2 seconds.
        Enforces dynamic Support/Resistance defense, trailing profit locks,
        50% theta decay profit-taking, and Thursday expiry square-offs.
        Returns number of closed contracts.
        """
        closed = 0
        now_dt = dt or datetime.now(IST)
        today_str = now_dt.strftime("%Y-%m-%d")
        is_expiry_square_off_time = (now_dt.hour > 15) or (now_dt.hour == 15 and now_dt.minute >= 15)

        positions = self.db.positions_by_product("FNO")

        for p in positions:
            symbol = p["symbol"]
            try:
                entry_credit = float(p["entry_price"])
                current_premium = float(p.get("current_price") or entry_credit)
                fno_cfg = self.cfg.get("fno", {})
                target_ratio = float(fno_cfg.get("profit_target_ratio", 0.50))
                target_premium = float(p.get("target") or (entry_credit * target_ratio))
                stop_loss_premium = float(p.get("stop_loss") or (entry_credit * 2.0))
                expiry_date = str(p.get("expiry_date") or "")
                underlying = "BANKNIFTY" if "BANKNIFTY" in symbol else "NIFTY"
                spot = 23250.0 if underlying == "NIFTY" else 54700.0
                if self.chain and hasattr(self.chain, "get_spot_price"):
                    spot = self.chain.get_spot_price(underlying)

                # Parse short strikes from symbol
                short_put = None
                short_call = None
                if "CONDOR-" in symbol:
                    parts = symbol.split("CONDOR-")[-1].split("/")
                    if len(parts) == 2:
                        try:
                            short_put = float(parts[0].replace("P", "").replace("C", ""))
                            short_call = float(parts[1].replace("P", "").replace("C", ""))
                        except Exception:
                            pass
                elif "BPS-" in symbol:
                    parts = symbol.split("BPS-")[-1].split("/")
                    if len(parts) >= 1:
                        try:
                            short_put = float(parts[0].replace("P", "").replace("C", ""))
                        except Exception:
                            pass
                elif "BCS-" in symbol:
                    parts = symbol.split("BCS-")[-1].split("/")
                    if len(parts) >= 1:
                        try:
                            short_call = float(parts[0].replace("P", "").replace("C", ""))
                        except Exception:
                            pass

                # 1. Dynamic Support & Resistance Defense Check (Runs first every 2 sec):
                # Only exit if spot is valid and breaks through S1 Support or R1 Resistance toward the short wing
                if self.sr_calc and spot > 0:
                    sr = self.sr_calc.calculate_levels(underlying, spot)
                    s1 = sr.get("support_1", 0.0)
                    r1 = sr.get("resistance_1", 999999.0)
                    baseline_close = float(sr.get("close") or spot)

                    # Baseline sanity check: baseline must be within 5% of spot to prevent mismatched exit
                    if abs(spot - baseline_close) / max(1.0, spot) < 0.05:
                        is_condor = "CONDOR" in symbol
                        is_bps = "BPS" in symbol or "Bull Put" in str(p.get("strategy", ""))
                        is_bcs = "BCS" in symbol or "Bear Call" in str(p.get("strategy", ""))

                        has_put_wing = is_condor or is_bps or (short_put is not None and not is_bcs)
                        has_call_wing = is_condor or is_bcs or (short_call is not None and not is_bps)

                        # Put wing defense (CONDOR or BPS): exit only if spot drops past support TOWARDS short put
                        if has_put_wing and s1 > 0 and spot < (s1 * 0.993):
                            if short_put is None or spot < (short_put * 1.01):
                                self.execution.close(symbol, current_premium, f"Dynamic S/R Defense ({underlying} S1 {s1} Violated)")
                                closed += 1
                                continue

                        # Call wing defense (CONDOR or BCS): exit only if spot rises past resistance TOWARDS short call
                        if has_call_wing and r1 < 999999 and spot > (r1 * 1.007):
                            if short_call is None or spot > (short_call * 0.99):
                                self.execution.close(symbol, current_premium, f"Dynamic S/R Defense ({underlying} R1 {r1} Violated)")
                                closed += 1
                                continue

                # Dynamic Option Premium Valuation (Theta decay & Spot delta/gamma response)
                is_already_triggered = (current_premium <= target_premium) or (current_premium >= stop_loss_premium)
                days_held = float(p.get("days_held") or 0.0)
                should_recalculate = (days_held > 0) or (current_premium == entry_credit)
                if not is_already_triggered and should_recalculate and p.get("opened_at") and expiry_date:
                    try:
                        opened = datetime.fromisoformat(str(p["opened_at"]).replace("Z", "+00:00")).astimezone(IST)
                        expiry_dt = datetime.strptime(expiry_date, "%Y-%m-%d").replace(hour=15, minute=30, tzinfo=IST)
                        total_span = max(1.0, (expiry_dt - opened).total_seconds())
                        days_held_secs = float(p.get("days_held") or 0.0) * 86400.0
                        elapsed = max(0.0, (now_dt - opened).total_seconds(), days_held_secs)
                        time_fraction = min(1.0, max(0.0, elapsed / total_span))

                        # Progressive Theta Decay (targets 50% profit decay towards Thursday)
                        decay_factor = max(0.10, 1.0 - (0.65 * (time_fraction ** 0.5)))

                        # Real-Time Spot Movement & Delta/Gamma Sensitivity:
                        # For OTM credit spreads (Bull Put Spread, Bear Call Spread, Iron Condor):
                        # Profit is maximized when spot stays safely away from short strikes.
                        # Premium only EXPANDS (adverse impact) if spot moves dangerously close to or breaches a short strike.
                        adverse_drift = 0.0
                        safe_buffer_pct = 0.010  # 1.0% minimum safe cushion (~230 pts on NIFTY, ~540 pts on BANKNIFTY)

                        if short_put is not None and short_call is not None:
                            # Iron Condor: two short wings
                            put_cushion = (spot - short_put) / short_put if short_put > 0 else 1.0
                            call_cushion = (short_call - spot) / short_call if short_call > 0 else 1.0
                            min_cushion = min(put_cushion, call_cushion)
                            if min_cushion < safe_buffer_pct:
                                adverse_drift = max(0.0, (safe_buffer_pct - min_cushion) / safe_buffer_pct)
                        elif short_put is not None:
                            # Bull Put Spread: adverse if spot falls towards short_put
                            put_cushion = (spot - short_put) / short_put if short_put > 0 else 1.0
                            if put_cushion < safe_buffer_pct:
                                adverse_drift = max(0.0, (safe_buffer_pct - put_cushion) / safe_buffer_pct)
                        elif short_call is not None:
                            # Bear Call Spread: adverse if spot rises towards short_call
                            call_cushion = (short_call - spot) / short_call if short_call > 0 else 1.0
                            if call_cushion < safe_buffer_pct:
                                adverse_drift = max(0.0, (safe_buffer_pct - call_cushion) / safe_buffer_pct)
                        else:
                            # Fallback using option_type and strike_price
                            opt_type = str(p.get("option_type", "")).upper()
                            strike = float(p.get("strike_price") or spot)
                            if "PE" in opt_type or "PUT" in opt_type:
                                cushion = (spot - strike) / strike if strike > 0 else 1.0
                                if cushion < safe_buffer_pct:
                                    adverse_drift = max(0.0, (safe_buffer_pct - cushion) / safe_buffer_pct)
                            elif "CE" in opt_type or "CALL" in opt_type:
                                cushion = (strike - spot) / strike if strike > 0 else 1.0
                                if cushion < safe_buffer_pct:
                                    adverse_drift = max(0.0, (safe_buffer_pct - cushion) / safe_buffer_pct)

                        if adverse_drift > 0.0:
                            spot_impact = 1.0 + (adverse_drift ** 1.5) * 1.5
                        else:
                            # Safe range: spot is well outside strikes, option enjoys steady decay
                            spot_impact = 1.0

                        current_premium = round(entry_credit * decay_factor * spot_impact, 2)
                        current_premium = max(0.05, min(entry_credit * 3.0, current_premium))
                        self.db.update_current_price(symbol, current_premium)
                    except Exception as val_err:
                        self.db.log("DEBUG", f"FNO valuation fallback for {symbol}: {val_err!r}")

                # 2. Expiry Day Final Square-Off (at 15:15 IST on expiry date)
                if expiry_date == today_str and is_expiry_square_off_time:
                    self.execution.close(symbol, current_premium, "Thursday Expiry Square-off")
                    closed += 1
                    continue

                # 3. Dynamic Multi-Tier Trailing Profit Locks:
                # Tier 1: At +25% profit (premium decayed by 25%), move stop loss to entry credit (breakeven lock)
                # Tier 2: At +40% profit (premium decayed by 40%), trail stop to entry * 0.80 (lock in +20% profit)
                if current_premium <= entry_credit * 0.60 and stop_loss_premium > entry_credit * 0.80:
                    stop_loss_premium = round(entry_credit * 0.80, 2)
                    try:
                        self.db.update_position_stops(symbol, stop_loss=stop_loss_premium, target=target_premium)
                    except Exception:
                        pass
                elif current_premium <= entry_credit * 0.75 and stop_loss_premium > entry_credit:
                    stop_loss_premium = entry_credit
                    try:
                        self.db.update_position_stops(symbol, stop_loss=entry_credit, target=target_premium)
                    except Exception:
                        pass

                # 4. Realistic Profit-Taking Rule (Locks in profit when theta decays to target)
                if current_premium <= target_premium:
                    decay_pct = int(round((1.0 - target_ratio) * 100))
                    reason = "50% Profit Target (Theta Decayed)" if decay_pct == 50 else f"Profit Target Reached ({decay_pct}% Theta Decayed)"
                    self.execution.close(symbol, current_premium, reason)
                    closed += 1
                    continue

                # 5. Stop Loss Rule (Premium expanded beyond stop loss limit)
                if current_premium >= stop_loss_premium:
                    self.execution.close(symbol, current_premium, "Option Stop Loss (Adverse Move)")
                    closed += 1
                    continue

            except Exception as e:
                self.db.log("ERROR", f"FNO position manager error for {symbol}: {e!r}")

        return closed


FnoPositionManager = FNOPositionManager
