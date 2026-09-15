from datetime import datetime, timezone

def validate_history(df, max_age_seconds=900, require_fresh=True):
    if df is None or df.empty:return False,"empty data"
    required={"Open","High","Low","Close","Volume"}
    if not required.issubset(df.columns):return False,"missing columns"
    if df[["Open","High","Low","Close","Volume"]].isnull().any().any():return False,"missing values"
    if (df[["Open","High","Low","Close"]] <= 0).any().any():return False,"invalid prices"
    if (df["High"] < df[["Open","Close"]].max(axis=1)).any():return False,"invalid high"
    if (df["Low"] > df[["Open","Close"]].min(axis=1)).any():return False,"invalid low"
    if df.index.duplicated().any():return False,"duplicate timestamps"
    if not df.index.is_monotonic_increasing:return False,"timestamps not ordered"
    if require_fresh:
        ts=df.index[-1]
        if getattr(ts,"tzinfo",None) is None:ts=ts.tz_localize("UTC")
        age=(datetime.now(timezone.utc)-ts.to_pydatetime()).total_seconds()
        if age > max_age_seconds:return False,f"stale data: {age:.0f}s"
    return True,"ok"
