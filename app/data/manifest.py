from pathlib import Path
import json
from datetime import datetime, timezone

class DatasetManifest:
    def __init__(self,path="data/dataset_manifest.json"):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)

    def record(self,source,kind,symbol,start,end,rows,adjusted=False):
        data=[]
        if self.path.exists():
            try:data=json.loads(self.path.read_text())
            except Exception:data=[]
        data.append({
            "source":source,"kind":kind,"symbol":symbol,
            "start":str(start),"end":str(end),"rows":int(rows),
            "adjusted":bool(adjusted),
            "recorded_at":datetime.now(timezone.utc).isoformat()
        })
        self.path.write_text(json.dumps(data,indent=2),encoding="utf-8")
