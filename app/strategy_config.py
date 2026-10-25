"""
Validated loader and resolution engine for config/strategy.json.
Enforces Rule 0: Nothing hard-coded. Every lot size, rate, and threshold
lives in config/strategy.json with an effective_from date.
"""

import json
from pathlib import Path
from datetime import datetime, date
from typing import Dict, Any, Union


REQUIRED_SECTIONS = {"meta", "contracts", "costs", "calendar", "sleeves", "portfolio_risk"}


class StrategyConfig:
    """Validated config holder with temporal resolution for rates and lot sizes."""

    def __init__(self, data: Dict[str, Any]):
        self._data = data
        self._validate()

    def _validate(self):
        missing = REQUIRED_SECTIONS - set(self._data.keys())
        if missing:
            raise KeyError(f"strategy.json missing required top-level sections: {sorted(missing)}")

        # Validate contracts
        contracts = self._data.get("contracts", {})
        for sym in ("NIFTY", "BANKNIFTY"):
            if sym not in contracts:
                raise KeyError(f"Missing contract definition for {sym}")
            c = contracts[sym]
            if "lot_schedule" not in c or not c["lot_schedule"]:
                raise KeyError(f"Contract {sym} missing lot_schedule")
            if "expiry_weekday" not in c:
                raise KeyError(f"Contract {sym} missing expiry_weekday")

        # Validate costs
        costs = self._data.get("costs", {})
        stt = costs.get("stt", {})
        for k in ("delivery", "intraday", "option_sell", "future_sell"):
            if k not in stt:
                raise KeyError(f"Costs missing STT key: {k}")

        # Validate calendar
        cal = self._data.get("calendar", {})
        if "supported_years" not in cal or not cal["supported_years"]:
            raise KeyError("Calendar missing supported_years")
        if "holidays" not in cal:
            raise KeyError("Calendar missing holidays")

        # Validate sleeves
        sleeves = self._data.get("sleeves", {})
        for s in ("A", "B", "C", "D"):
            if s not in sleeves:
                raise KeyError(f"Sleeves configuration missing sleeve {s}")

    @property
    def raw(self) -> Dict[str, Any]:
        return self._data

    def get_sleeve_config(self, sleeve: str) -> Dict[str, Any]:
        if sleeve not in self._data["sleeves"]:
            raise KeyError(f"Unknown sleeve: {sleeve}")
        return self._data["sleeves"][sleeve]

    def get_lot_size(self, symbol: str, asof: Union[date, datetime, str]) -> int:
        """Resolve contract lot size based on effective_from date schedule."""
        sym = symbol.upper()
        if sym not in self._data["contracts"]:
            raise KeyError(f"No contract definition for symbol: {symbol}")

        target_date = str(asof)[:10]
        schedule = self._data["contracts"][sym]["lot_schedule"]
        # Sort ascending by effective_from
        sorted_sched = sorted(schedule, key=lambda x: str(x["effective_from"]))

        current_lot = None
        for entry in sorted_sched:
            if str(entry["effective_from"]) <= target_date:
                current_lot = int(entry["lot"])
            else:
                break

        if current_lot is None:
            # Fall back to first available schedule entry
            current_lot = int(sorted_sched[0]["lot"])
        return current_lot

    def get_expiry_weekday(self, symbol: str) -> str:
        sym = symbol.upper()
        if sym not in self._data["contracts"]:
            raise KeyError(f"No contract definition for symbol: {symbol}")
        return self._data["contracts"][sym]["expiry_weekday"]

    def assert_weekly_allowed(self, symbol: str):
        """Enforces market fact: BANKNIFTY has monthly expiry only (no weekly)."""
        sym = symbol.upper()
        if sym not in self._data["contracts"]:
            raise KeyError(f"No contract definition for symbol: {symbol}")
        if not self._data["contracts"][sym].get("weekly_enabled", True):
            raise ValueError(f"{sym} does not support weekly options per regulatory/exchange schedule")

    def get_stt_rate(self, segment: str, asof: Union[date, datetime, str], side: str = "SELL") -> float:
        """
        Resolve STT rate based on segment and effective date.
        delivery: 0.1% (both buy and sell)
        intraday: 0.025% (sell side only)
        option_sell: 0.1% before 2026-04-01; 0.15% from 2026-04-01
        future_sell: 0.02% before 2026-04-01; 0.05% from 2026-04-01
        """
        stt_cfg = self._data["costs"]["stt"]
        seg = segment.lower()
        target_date = str(asof)[:10]

        if seg == "delivery":
            return float(stt_cfg["delivery"])

        if seg == "intraday":
            return float(stt_cfg["intraday"]) if side.upper() == "SELL" else 0.0

        if seg in ("options", "option"):
            if side.upper() != "SELL":
                return 0.0
            sched = sorted(stt_cfg["option_sell"], key=lambda x: str(x["effective_from"]))
            rate = float(sched[0]["rate"])
            for entry in sched:
                if str(entry["effective_from"]) <= target_date:
                    rate = float(entry["rate"])
                else:
                    break
            return rate

        if seg in ("futures", "future"):
            if side.upper() != "SELL":
                return 0.0
            sched = sorted(stt_cfg["future_sell"], key=lambda x: str(x["effective_from"]))
            rate = float(sched[0]["rate"])
            for entry in sched:
                if str(entry["effective_from"]) <= target_date:
                    rate = float(entry["rate"])
                else:
                    break
            return rate

        return 0.0


def load_strategy_config(path: Union[str, Path] = "config/strategy.json") -> StrategyConfig:
    p = Path(path)
    if not p.is_absolute():
        root = Path(__file__).resolve().parent.parent
        p = root / path
    if not p.exists():
        raise FileNotFoundError(f"Strategy config file not found at {p}")
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    return StrategyConfig(data)
