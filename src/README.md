# School Payment Tracker

Fee collection and tracking for a school (LKG–10), built with Streamlit and SQLite.

## What it does

- **Students**: admission numbers, yearly class / section / roll number, category (Management, DG 1, DG 2),
  Aadhaar stored with AES-256-GCM encryption, guardians shared between siblings, leaving / passing out.
- **Fees**: monthly tuition per class per term (June → May), optional per-student van fee (start / stop any
  month), one-off fees (books, uniform, custom). Students who join mid-year pay from their joining month.
- **Billing**: search by ID / admission no / name + class, month-by-month dues grid, part payments,
  "fill oldest first", printable receipts (`RCPT/2026-27/00001`), voids with reasons. Balances never carry
  over between terms.
- **Analytics**: paid-up vs defaulters, collected / overdue / remaining, monthly trends, class / mode /
  category breakdowns, term comparison, downloadable list of students who have not paid.
- **Excel reports**: monthly (paid only / all students), financial year (Apr–Mar, by payment date),
  school term (Jun–May, student × month balances), custom range with filters.
- **Backup & restore**: weekly automatic `.db` backups, on-demand backup, Excel export of every table,
  restore from either format, optional e-mail delivery.
- **Users**: Admin (everything) and Biller (students + billing; no voids, no admin pages).

## Running it

### Windows (single computer)
1. Install Python 3.10 from python.org (tick *Add to PATH*).
2. Double-click `run.bat`. The first start installs packages; the browser opens at http://localhost:8501.
3. Other computers on the same network can use `http://<this-computer's-IP>:8501`.

### Docker
```bash
docker compose up -d --build        # http://<host>:8501
```
`data_store/`, `secrets/` and `logs/` are mounted from the host, so data survives rebuilds.

### First start
- The database is created (or the prototype database is upgraded automatically, after a backup).
- You are asked to create the administrator account.
- Go to **Admin → Terms & fees**: check the current term, enter monthly tuition per class, press
  **Apply to students**, and fill in **School details** (shown on receipts).

## Important: backups and the encryption key

| What | Where | Notes |
|---|---|---|
| Database | `data_store/database.db` | Never edit by hand. |
| Backups | `data_store/backups/` | Weekly automatic while the app runs; keep copies off this computer. |
| Aadhaar key | `secrets/identifier.key` | **Not inside any backup.** Copy it to a safe place once. Without it, full Aadhaar numbers cannot be read after moving to a new computer (everything else still works). |

Weekly backups even when the app is closed (Windows): Task Scheduler → *Create Basic Task* → weekly →
*Start a program* → `backup.bat` in this folder.

## Configuration (environment variables, all optional)

| Variable | Default | Meaning |
|---|---|---|
| `SPT_FEE_DUE_DAY` | `10` | Day of the month a monthly fee becomes overdue |
| `SPT_DB_PATH` / `SPT_BACKUP_DIR` / `SPT_LOG_DIR` | `data_store/...`, `logs/` | Alternative locations |
| `SPT_IDENTIFIER_KEY` | – | Base64 key instead of the key file |
| `SPT_SMTP_HOST`, `SPT_SMTP_PORT`, `SPT_SMTP_USER`, `SPT_SMTP_PASSWORD`, `SPT_SMTP_SENDER`, `SPT_BACKUP_EMAIL_TO` | – | E-mail backups (Gmail: use an app password, host `smtp.gmail.com`, port 587) |

## Rules worth knowing

- A month's fee is **overdue** from `SPT_FEE_DUE_DAY` of that month; one-off fees are due when added.
  For a finished term every unpaid fee counts.
- Receipts cannot be edited or deleted — void them (admin) and issue a new one. SQLite triggers enforce
  this, plus "never allocate more than is due", "never more than the receipt", and "no carry-over".
- Promotion (Admin → Promotion) closes a term per class and opens the next term with fresh tuition fees.
  Van is not carried over. Class 10 → *Passed out*.

## Development

```bash
pip install -r requirements-dev.txt
pytest                      # unit, migration, integrity, service, report, backup and UI tests
python -m data_management.migrations   # apply migrations manually
python -m backup_and_restore           # take a backup from the command line
```

```
app.py                      entry point: startup, role-based navigation
config/settings.py          paths, time zone, due day, SMTP
statics.py                  classes, sections, fee types, enums
helper/                     clock (IST), money (paise, ₹ formatting, words), school calendar, logging
data_management/
  dao/                      SQLModel table classes
  dto/                      Pydantic input / output models (all validation)
  repositories/             SQL queries
  services/                 business logic + transactions (UI calls only these)
  migrations/               versioned schema changes (never edit an applied one)
reports/                    Excel builder, printable receipt
backup_and_restore/         backups, restore, scheduler, CLI
ui/                         Streamlit pages
tests/                      pytest suite
```

Conventions: money is stored as integer **paise**; timestamps are naive **IST**; the schema is owned by
migrations (add `mNNN_*.py`, never `create_all`).
