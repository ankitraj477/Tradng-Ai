import threading
import time
from datetime import datetime, timezone


class IsolatedProtectionWorker:
    """
    Dedicated position protection worker.
    Runs on an isolated thread/process to ensure real-time stop-loss management
    is never blocked or stalled by slow scanner downloads, ML retraining, or news feeds.
    Communicates strictly via the database state.
    """
    def __init__(self, position_manager, interval_seconds=1.0):
        self.manager = position_manager
        self.interval = float(interval_seconds)
        self._running = False
        self._thread = None
        self.last_heartbeat = None
        self.cycle_count = 0
        self.errors = []

    def run_cycle(self):
        """Executes a single protected position management cycle."""
        try:
            self.manager.manage()
            self.cycle_count += 1
            self.last_heartbeat = datetime.now(timezone.utc)
            return True
        except Exception as e:
            self.errors.append(str(e))
            return False

    def _loop(self):
        while self._running:
            self.run_cycle()
            time.sleep(self.interval)

    def start(self):
        if self._running: return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="ProtectionWorker")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def is_alive(self):
        return bool(self._running and self._thread and self._thread.is_alive())
