import pytest
from app.version import __version__, VERSION
from app.dashboard import create_app
from app.db import DB
from scripts.bump_version import bump_version, parse_semver, get_current_version

def test_version_constants():
    assert __version__ == VERSION
    assert len(__version__.split(".")) >= 2
    assert get_current_version() == __version__

def test_semver_bumping_logic():
    assert bump_version("7.3.0", "patch") == "7.3.1"
    assert bump_version("7.3.9", "patch") == "7.3.10"
    assert bump_version("7.3.0", "minor") == "7.4.0"
    assert bump_version("7.3.0", "major") == "8.0.0"
    assert bump_version("7.3.0", explicit="7.5.0") == "7.5.0"

def test_dashboard_version_endpoints(tmp_path):
    db = DB(str(tmp_path / "test_ver.db"))
    db.init()
    db.ensure_account(1000.0, 10000.0)

    app = create_app(db=db, cfg={"dashboard": {"token": "test"}})
    client = app.test_client()

    # 1. Health check returns __version__
    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.get_json()["version"] == __version__

    # 2. State check returns __version__
    res_state = client.get("/api/state")
    assert res_state.status_code == 200
    assert res_state.get_json()["version"] == __version__

    # 3. HTML template includes dynamic version
    res_index = client.get("/")
    assert res_index.status_code == 200
    html = res_index.get_data(as_text=True)
    assert f"PRO v{__version__}" in html
    assert f"?v={__version__}" in html
