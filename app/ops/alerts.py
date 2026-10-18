import time
from datetime import datetime, timezone


class AlertSink:
    def send(self, alert):
        raise NotImplementedError


class MemoryAlertSink(AlertSink):
    """In-memory alert sink for test verification and dashboard diagnostics."""
    def __init__(self):
        self.alerts = []

    def send(self, alert):
        self.alerts.append(alert)


class AlertManager:
    """
    Central operational alert manager.
    Dispatches alerts on data outages, kill switch triggers, and drawdown breaches.
    Enforces alert throttling to prevent notification storms.
    """
    def __init__(self, sinks=None, throttle_seconds=900):
        self.sinks = list(sinks or [MemoryAlertSink()])
        self.throttle_sec = int(throttle_seconds)
        self._last_sent = {}

    def emit(self, level, category, message, details=None):
        now = time.time()
        key = f"{level}:{category}"
        if now - self._last_sent.get(key, 0) < self.throttle_sec:
            return False  # Throttled

        self._last_sent[key] = now
        alert = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level.upper(),  # INFO, WARN, CRITICAL
            "category": category.upper(),  # DATA_OUTAGE, KILL_SWITCH, DRAWDOWN
            "message": message,
            "details": details or {}
        }

        for s in self.sinks:
            try:
                s.send(alert)
            except Exception:
                pass
        return True

    def get_alerts(self):
        for s in self.sinks:
            if isinstance(s, MemoryAlertSink):
                return s.alerts
        return []
