import pandas as pd
from app.data.validator import validate_history

def frame(index):
    return pd.DataFrame({'Open':[10,11],'High':[11,12],'Low':[9,10],'Close':[10.5,11.5],'Volume':[100,120]},index=index)

def test_validator_rejects_unordered_timestamps():
    idx=pd.to_datetime(['2026-09-15 09:20','2026-09-15 09:15'])
    ok,msg=validate_history(frame(idx),require_fresh=False)
    assert not ok and 'ordered' in msg

def test_validator_can_check_cached_data_without_freshness_gate():
    idx=pd.to_datetime(['2026-09-15 09:15','2026-09-15 09:20'])
    ok,msg=validate_history(frame(idx),require_fresh=False)
    assert ok and msg=='ok'
