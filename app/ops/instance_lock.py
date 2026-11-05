"""
Single instance process lock to prevent concurrent trading engines
from clobbering the database or consuming duplicate resources.
"""
import os
import atexit
import logging

logger = logging.getLogger("tradng_ai.lock")


class SingleInstanceLock:
    def __init__(self, lockfile_path="data/engine.lock"):
        self.lockfile_path = lockfile_path
        self.fp = None

    def acquire(self) -> bool:
        """Attempts to acquire exclusive lock on lockfile. Returns True on success, False if already held."""
        try:
            os.makedirs(os.path.dirname(self.lockfile_path), exist_ok=True)
            self.fp = open(self.lockfile_path, "a+")
            if os.name == "nt":
                import msvcrt
                try:
                    self.fp.seek(0)
                    msvcrt.locking(self.fp.fileno(), msvcrt.LK_NBLCK, 1)
                except (OSError, IOError):
                    self.fp.close()
                    self.fp = None
                    return False
            else:
                import fcntl
                try:
                    fcntl.flock(self.fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (OSError, IOError):
                    self.fp.close()
                    self.fp = None
                    return False

            self.fp.seek(0)
            self.fp.truncate()
            self.fp.write(f"{os.getpid()}\n")
            self.fp.flush()
            atexit.register(self.release)
            return True
        except Exception as e:
            logger.warning(f"Could not verify process lock: {e}")
            return True  # fallback if file permissions issue

    def release(self):
        """Releases the lock upon process termination."""
        try:
            if self.fp and not self.fp.closed:
                if os.name == "nt":
                    import msvcrt
                    try:
                        self.fp.seek(0)
                        msvcrt.locking(self.fp.fileno(), msvcrt.LK_UNLCK, 1)
                    except Exception:
                        pass
                else:
                    import fcntl
                    try:
                        fcntl.flock(self.fp.fileno(), fcntl.LOCK_UN)
                    except Exception:
                        pass
                self.fp.close()
                self.fp = None
        except Exception:
            pass
