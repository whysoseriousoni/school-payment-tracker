# School Payment Tracker

Fee collection and tracking for a school (LKG–10), built with Streamlit and SQLite.

## What it does

- **Students**: admission numbers, yearly class / section / roll number, category (Management, DG 1, DG 2),
  Aadhaar stored with AES-256-GCM encryption, guardians shared between siblings, leaving / passing out.
- **Fee plans**: named annual fees per term, e.g. `UKG-FEE-1` ₹10,000, `UKG-FEE-2` ₹9,000,
  `UKG-DG1-1` ₹5,000. Tuition plans are per class and optionally per category (Management, DG 1, DG 2);
  van plans apply to any class. One default plan per class + category is assigned automatically;
  any student can be moved to another plan or given a custom amount (with a reason). Plans and
  milestones can be copied into the next term with a % increase.
- **Flexible payment**: parents pay any amount, any time (usually up to 12 instalments; the biller is
  warned after 12). Payment milestones per term (e.g. 50% by 31 Oct, 100% by 31 Mar) decide who is
  behind. One-off fees (books, uniform, custom) are added per student.
- **Billing**: search by ID / admission no / name + class, fees with paid / balance / overdue,
  instalments used, printable receipts (`RCPT/2026-27/00001`), voids with reasons. Balances never
  carry over between terms.
- **Analytics**: paid-up vs defaulters, collected / overdue / remaining, monthly trends, class / mode /
  category breakdowns, term comparison, downloadable list of students who have not paid.
- **Excel reports**: monthly (paid only / all students), financial year (Apr–Mar, by payment date),
  school term (Jun–May: student balances, amount paid per month), custom range with filters.
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
- **Admin → Terms & school**: check the current term and fill in the school details (shown on receipts).
- **Admin → Fee plans**: add the plans for each class (tick *Default* for the usual one, add category
  defaults such as `UKG-DG1-1`), set the **payment milestones**, then **Assign default plans** and move
  individual students to other plans where needed.

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
| `SPT_DB_PATH` / `SPT_BACKUP_DIR` / `SPT_LOG_DIR` | `data_store/...`, `logs/` | Alternative locations |
| `SPT_IDENTIFIER_KEY` | – | Base64 key instead of the key file |
| `SPT_SMTP_HOST`, `SPT_SMTP_PORT`, `SPT_SMTP_USER`, `SPT_SMTP_PASSWORD`, `SPT_SMTP_SENDER`, `SPT_BACKUP_EMAIL_TO` | – | E-mail backups (Gmail: use an app password, host `smtp.gmail.com`, port 587) |

## Rules worth knowing

- On any date, the **expected** share of each annual fee is the highest milestone % already reached; at
  the end of the term the whole fee is expected. Overdue = expected − paid (receipts dated up to that
  date). One-off fees are expected from the day they are added.
- Changing a plan's amount updates every student on it, except students who already paid more than the
  new amount (they are listed). A student who leaves has unpaid annual fees reduced to what was paid.
- Receipts cannot be edited or deleted — void them (admin) and issue a new one. SQLite triggers enforce
  this, plus "never allocate more than is due", "never more than the receipt", and "no carry-over".
- Promotion (Admin → Promotion) closes a term per class and opens the next term with the new term's
  default plan for each student's class and category. Van is not carried over. Class 10 → *Passed out*.

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
