from pathlib import Path
import json
from datetime import datetime, timezone


class DatasetManifest:
    def __init__(
        self,
        path="data/dataset_manifest.json",
    ):
        self.path = Path(path)
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        self._records = None

    def _load(self):
        if self._records is not None:
            return self._records

        if not self.path.exists():
            self._records = []
            return self._records

        try:
            value = json.loads(
                self.path.read_text(
                    encoding="utf-8"
                )
            )

            self._records = (
                value
                if isinstance(value, list)
                else []
            )

        except (OSError, ValueError):
            self._records = []

        return self._records

    def record(
        self,
        source,
        kind,
        symbol,
        start,
        end,
        rows,
        adjusted=False,
    ):
        records = self._load()

        key = (
            str(source),
            str(kind),
            str(symbol),
            str(start),
            str(end),
            int(rows),
            bool(adjusted),
        )

        for record in records:
            existing = (
                record.get("source"),
                record.get("kind"),
                record.get("symbol"),
                record.get("start"),
                record.get("end"),
                int(record.get("rows", 0)),
                bool(record.get("adjusted", False)),
            )

            if existing == key:
                return

        records.append(
            {
                "source": source,
                "kind": kind,
                "symbol": symbol,
                "start": str(start),
                "end": str(end),
                "rows": int(rows),
                "adjusted": bool(adjusted),
                "recorded_at": (
                    datetime.now(timezone.utc)
                    .isoformat()
                ),
            }
        )

        tmp = self.path.with_suffix(
            self.path.suffix + ".tmp"
        )

        tmp.write_text(
            json.dumps(
                records,
                indent=2,
            ),
            encoding="utf-8",
        )

        tmp.replace(self.path)