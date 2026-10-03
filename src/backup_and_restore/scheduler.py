"""In-process weekly backup: checks hourly while the app server is running."""
import threading
import time

from backup_and_restore.service import run_scheduled_backup_if_due
from helper.logger import get_logger

logger = get_logger(__name__)
_CHECK_EVERY_SECONDS = 3600
_started = False
_lock = threading.Lock()


def _loop() -> None:
    while True:
        try:
            path = run_scheduled_backup_if_due()
            if path:
                logger.info("Automatic weekly backup created: %s", path)
        except Exception:
            logger.exception("Automatic backup failed")
        time.sleep(_CHECK_EVERY_SECONDS)


def start_backup_scheduler() -> None:
    global _started
    with _lock:
        if _started:
            return
        threading.Thread(target=_loop, name="weekly-backup", daemon=True).start()
        _started = True
