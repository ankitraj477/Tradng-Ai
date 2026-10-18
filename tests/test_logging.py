from pathlib import Path
import pytest
from app.logger import setup_logging, get_logger, read_recent_logs
from app.db import DB
from app.dashboard import create_app


def test_logger_setup_and_write():
    logger = setup_logging(log_level="DEBUG")
    assert logger is not None

    test_msg = "TEST_DEBUG_MESSAGE_FOR_VERIFICATION_12345"
    logger.debug(test_msg)

    # Read back recent logs
    recent = read_recent_logs(max_lines=50)
    assert any(test_msg in line for line in recent)


def test_db_log_pipes_to_logger():
    setup_logging(log_level="INFO")
    db = DB(":memory:")
    
    test_db_msg = "DB_LOG_PIPED_TEST_MESSAGE_67890"
    db.log("INFO", test_db_msg)

    # Verify message appears in rotating log file
    recent = read_recent_logs(max_lines=50)
    assert any(test_db_msg in line for line in recent)


def test_dashboard_logs_endpoint():
    db = DB(":memory:")
    db.ensure_account(1000.0, 100000.0)
    app = create_app(db=db)
    client = app.test_client()

    res = client.get("/api/logs?lines=20")
    assert res.status_code == 200
    assert "logs" in res.json
    assert isinstance(res.json["logs"], list)
    assert "count" in res.json
