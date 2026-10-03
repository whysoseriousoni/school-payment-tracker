"""
Command line backup, for Windows Task Scheduler / cron:
    python -m backup_and_restore            take a backup now
    python -m backup_and_restore --if-due   only if the last weekly backup is 7+ days old
"""
import sys

from backup_and_restore.service import create_backup, prune_automatic_backups, run_scheduled_backup_if_due
from helper.logger import configure_logging


def main() -> int:
    configure_logging()
    if "--if-due" in sys.argv:
        path = run_scheduled_backup_if_due()
        print(f"Backup created: {path}" if path else "A recent weekly backup exists; nothing to do.")
    else:
        path = create_backup("weekly")
        prune_automatic_backups()
        print(f"Backup created: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
