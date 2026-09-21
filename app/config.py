import json
import os
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]

load_dotenv(ROOT / ".env")


def load_config():
    with open(
        ROOT / "config" / "default.json",
        "r",
        encoding="utf-8",
    ) as f:
        cfg = json.load(f)

    cfg["capital"]["starting"] = float(
        os.getenv(
            "STARTING_CAPITAL",
            cfg["capital"]["starting"],
        )
    )

    cfg["capital"]["target"] = float(
        os.getenv(
            "TARGET_CAPITAL",
            cfg["capital"]["target"],
        )
    )

    cfg["market"]["decision_interval_minutes"] = int(
        os.getenv(
            "DECISION_INTERVAL_MINUTES",
            cfg["market"]["decision_interval_minutes"],
        )
    )

    cfg["market"]["data_max_age_seconds"] = int(
        os.getenv(
            "DATA_MAX_AGE_SECONDS",
            cfg["market"]["data_max_age_seconds"],
        )
    )

    cfg["market"]["live_data_max_age_seconds"] = int(
        os.getenv(
            "LIVE_DATA_MAX_AGE_SECONDS",
            cfg["market"].get(
                "live_data_max_age_seconds",
                420,
            ),
        )
    )

    cfg["market"]["min_fresh_data_coverage_pct"] = float(
        os.getenv(
            "MIN_FRESH_DATA_COVERAGE_PCT",
            cfg["market"].get(
                "min_fresh_data_coverage_pct",
                0.70,
            ),
        )
    )

    cfg["market"]["max_candidates"] = int(
        os.getenv(
            "MAX_CANDIDATES",
            cfg["market"]["max_candidates"],
        )
    )

    cfg["risk"]["max_position_risk_pct"] = float(
        os.getenv(
            "MAX_POSITION_RISK_PCT",
            cfg["risk"]["max_position_risk_pct"],
        )
    )

    cfg["risk"]["emergency_drawdown_pct"] = float(
        os.getenv(
            "EMERGENCY_DRAWDOWN_PCT",
            cfg["risk"]["emergency_drawdown_pct"],
        )
    )

    cfg["live_data"] = (
        os.getenv(
            "LIVE_DATA",
            "false",
        ).lower()
        == "true"
    )

    cfg["use_cpp_scanner"] = (
        os.getenv(
            "USE_CPP_SCANNER",
            "false",
        ).lower()
        == "true"
    )

    cfg["allow_shorts"] = (
        os.getenv(
            "ALLOW_SHORTS",
            "true",
        ).lower()
        == "true"
    )

    cfg["database_path"] = os.getenv(
        "DATABASE_PATH",
        str(ROOT / "data" / "trader.db"),
    )

    return cfg