# Operational Safety & Process Rules

When starting, restarting, or managing Tradng-Ai engine processes:

1. **Singleton Process Execution**: Never launch concurrent instances of `run.py` or multiple instances of the same desk runner against `data/trader.db`. Always verify that `app.ops.instance_lock.SingleInstanceLock` succeeds.
2. **Graceful Shutdown**: Always allow background threads to terminate cleanly so SQLite finishes committing write-ahead log (WAL) frames (`PRAGMA wal_checkpoint(TRUNCATE)`).
3. **Port Conflict Avoidance**: Ensure port 5000 (or `APP_PORT`) is free before launching Flask web servers.
4. **Heartbeat Monitoring**: The engine updates `db._last_cycle_at`. If the heartbeat interval exceeds 3x `decision_interval_minutes`, flag a stalled engine alert.
5. **Exception Counters**: Inspect `db._exception_counts` for scanner, news, or protection subsystem failures before reporting an operational health pass.
