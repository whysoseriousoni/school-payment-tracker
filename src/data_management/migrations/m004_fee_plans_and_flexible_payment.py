"""
Migration 004 - fee plans and flexible (annual) payment.

* fee_plan: named annual fees per term, e.g. UKG-FEE-1 Rs 10,000, UKG-DG1-1 Rs 5,000
  (tuition plans are per class and optionally per category; van plans are any class).
* fee_milestone: "x% of the annual fee due by date" rules per term (for overdue reports).
* student_fee_due: tuition and van become ONE annual due per enrollment, linked to the
  assigned plan (or a custom amount with a reason). One-off fees are unchanged.
* fee_structure (monthly amounts) is converted into default tuition / van plans and dropped.

Existing monthly dues of an enrollment are merged into one annual due; their payment
allocations are merged onto it, so every balance stays exactly the same (checked below).
"""
import sqlite3
from collections import defaultdict

from data_management.migrations.runner import LogFn, MigrationError, execute_script
from helper.clock import now_ist

VERSION = 4
NAME = "fee plans and flexible payment"

_DT_FORMAT = "%Y-%m-%d %H:%M:%S.%f"
ANNUAL_TYPES = ("TUITION", "VAN")
CONVERTED_REASON = "Converted from monthly fees"

NEW_TABLES_SQL = """
CREATE TABLE fee_plan (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    academic_year_id    INTEGER NOT NULL REFERENCES academic_year (id) ON DELETE RESTRICT,
    code                TEXT    NOT NULL COLLATE NOCASE CHECK (trim(code) <> ''),
    fee_type            TEXT    NOT NULL CHECK (fee_type IN ('TUITION', 'VAN')),
    student_class       TEXT,
    category            TEXT,
    annual_amount_paise INTEGER NOT NULL CHECK (annual_amount_paise >= 0),
    is_default          INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
    is_active           INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    description         TEXT,
    inserted_on         DATETIME NOT NULL,
    updated_on          DATETIME NOT NULL,
    UNIQUE (academic_year_id, code),
    CHECK (fee_type <> 'TUITION' OR student_class IS NOT NULL),
    CHECK (is_default = 0 OR is_active = 1)
);
CREATE UNIQUE INDEX ux_fee_plan_one_default ON fee_plan
    (academic_year_id, fee_type, COALESCE(student_class, ''), COALESCE(category, '')) WHERE is_default = 1;

CREATE TABLE fee_milestone (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    academic_year_id   INTEGER NOT NULL REFERENCES academic_year (id) ON DELETE CASCADE,
    due_date           DATE    NOT NULL,
    cumulative_percent INTEGER NOT NULL CHECK (cumulative_percent BETWEEN 1 AND 100),
    inserted_on        DATETIME NOT NULL,
    updated_on         DATETIME NOT NULL,
    UNIQUE (academic_year_id, due_date)
);

CREATE TABLE student_fee_due_v4 (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    enrollment_id    INTEGER NOT NULL REFERENCES student_enrollment (id) ON DELETE RESTRICT,
    fee_type         TEXT    NOT NULL,
    fee_plan_id      INTEGER REFERENCES fee_plan (id) ON DELETE RESTRICT,
    description      TEXT,
    override_reason  TEXT,
    amount_due_paise INTEGER NOT NULL CHECK (amount_due_paise >= 0),
    inserted_on      DATETIME NOT NULL,
    updated_on       DATETIME NOT NULL,
    -- Only annual fees (tuition, van) come from a plan; they need a plan or a reason for a custom amount.
    CHECK (fee_type IN ('TUITION', 'VAN') OR fee_plan_id IS NULL),
    CHECK (fee_type NOT IN ('TUITION', 'VAN') OR fee_plan_id IS NOT NULL
           OR (override_reason IS NOT NULL AND trim(override_reason) <> ''))
);

CREATE TABLE payment_allocation_v4 (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id   INTEGER NOT NULL REFERENCES payment (id) ON DELETE CASCADE,
    fee_due_id   INTEGER NOT NULL REFERENCES student_fee_due (id) ON DELETE RESTRICT,
    amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
    UNIQUE (payment_id, fee_due_id)
);
"""

FINAL_OBJECTS_SQL = """
CREATE UNIQUE INDEX ux_fee_due_annual ON student_fee_due (enrollment_id, fee_type) WHERE fee_type IN ('TUITION', 'VAN');
CREATE INDEX ix_fee_due_enrollment ON student_fee_due (enrollment_id);
CREATE INDEX ix_fee_due_plan ON student_fee_due (fee_plan_id);
CREATE INDEX ix_allocation_fee_due ON payment_allocation (fee_due_id);

CREATE TRIGGER trg_fee_due_plan_matches_insert
BEFORE INSERT ON student_fee_due
WHEN NEW.fee_plan_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Fee plan does not match this fee type or term')
    WHERE NOT EXISTS (
        SELECT 1 FROM fee_plan fp JOIN student_enrollment e ON e.id = NEW.enrollment_id
         WHERE fp.id = NEW.fee_plan_id AND fp.fee_type = NEW.fee_type AND fp.academic_year_id = e.academic_year_id);
END;

CREATE TRIGGER trg_fee_due_plan_matches_update
BEFORE UPDATE OF fee_plan_id ON student_fee_due
WHEN NEW.fee_plan_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Fee plan does not match this fee type or term')
    WHERE NOT EXISTS (
        SELECT 1 FROM fee_plan fp JOIN student_enrollment e ON e.id = NEW.enrollment_id
         WHERE fp.id = NEW.fee_plan_id AND fp.fee_type = NEW.fee_type AND fp.academic_year_id = e.academic_year_id);
END;

CREATE TRIGGER trg_allocation_rules
BEFORE INSERT ON payment_allocation
BEGIN
    SELECT RAISE(ABORT, 'Cannot allocate a voided payment')
    WHERE (SELECT is_voided FROM payment WHERE id = NEW.payment_id) = 1;

    SELECT RAISE(ABORT, 'Payment and fee due belong to different enrollments (no carry-over across years)')
    WHERE (SELECT enrollment_id FROM payment WHERE id = NEW.payment_id)
       <> (SELECT enrollment_id FROM student_fee_due WHERE id = NEW.fee_due_id);

    SELECT RAISE(ABORT, 'Allocations exceed the payment amount')
    WHERE (SELECT COALESCE(SUM(amount_paise), 0) FROM payment_allocation WHERE payment_id = NEW.payment_id)
          + NEW.amount_paise
        > (SELECT amount_paise FROM payment WHERE id = NEW.payment_id);

    SELECT RAISE(ABORT, 'Allocations exceed the amount due')
    WHERE (SELECT COALESCE(SUM(a.amount_paise), 0)
             FROM payment_allocation a JOIN payment p ON p.id = a.payment_id
            WHERE a.fee_due_id = NEW.fee_due_id AND p.is_voided = 0)
          + NEW.amount_paise
        > (SELECT amount_due_paise FROM student_fee_due WHERE id = NEW.fee_due_id);
END;

CREATE TRIGGER trg_allocation_immutable
BEFORE UPDATE ON payment_allocation
BEGIN
    SELECT RAISE(ABORT, 'Allocations are immutable; void the payment instead');
END;

CREATE TRIGGER trg_fee_due_not_below_paid
BEFORE UPDATE OF amount_due_paise ON student_fee_due
WHEN NEW.amount_due_paise < (
    SELECT COALESCE(SUM(a.amount_paise), 0)
      FROM payment_allocation a JOIN payment p ON p.id = a.payment_id
     WHERE a.fee_due_id = NEW.id AND p.is_voided = 0)
BEGIN
    SELECT RAISE(ABORT, 'Amount due cannot be reduced below the amount already paid');
END;

CREATE VIEW v_fee_due_status AS
SELECT d.id                 AS fee_due_id,
       d.enrollment_id,
       e.student_id,
       e.academic_year_id,
       e.student_class,
       e.section,
       d.fee_type,
       d.fee_plan_id,
       fp.code              AS plan_code,
       d.description,
       d.override_reason,
       d.amount_due_paise,
       COALESCE(SUM(CASE WHEN p.is_voided = 0 THEN a.amount_paise END), 0) AS amount_paid_paise,
       d.amount_due_paise
         - COALESCE(SUM(CASE WHEN p.is_voided = 0 THEN a.amount_paise END), 0) AS balance_paise,
       substr(d.inserted_on, 1, 10) AS created_on
  FROM student_fee_due d
  JOIN student_enrollment e ON e.id = d.enrollment_id
  LEFT JOIN fee_plan fp ON fp.id = d.fee_plan_id
  LEFT JOIN payment_allocation a ON a.fee_due_id = d.id
  LEFT JOIN payment p ON p.id = a.payment_id
 GROUP BY d.id;
"""


def _scalar(conn: sqlite3.Connection, sql: str) -> int:
    return conn.execute(sql).fetchone()[0] or 0


def _balances(conn: sqlite3.Connection, view: str = "v_fee_due_status") -> dict:
    return {row[0]: (row[1], row[2]) for row in conn.execute(
        f"SELECT enrollment_id, SUM(amount_due_paise), SUM(amount_paid_paise) FROM {view} GROUP BY enrollment_id")}


def upgrade(conn: sqlite3.Connection, log: LogFn) -> None:
    stamp = now_ist().strftime(_DT_FORMAT)
    balances_before = _balances(conn)
    allocated_before = _scalar(conn, "SELECT SUM(amount_paise) FROM payment_allocation")

    for statement in ("DROP VIEW v_fee_due_status", "DROP TRIGGER trg_allocation_rules",
                      "DROP TRIGGER trg_allocation_immutable", "DROP TRIGGER trg_fee_due_not_below_paid"):
        conn.execute(statement)
    execute_script(conn, NEW_TABLES_SQL)

    # ---- monthly fee structures -> default annual plans
    plan_ids = {}  # (year_id, class, fee_type) -> (plan_id, annual paise)
    for row in conn.execute("SELECT * FROM fee_structure ORDER BY id").fetchall():
        annual = row["monthly_amount_paise"] * 12
        if row["fee_type"] == "TUITION":
            code, plan_class = f"{row['student_class']}-FEE-1", row["student_class"]
        else:
            code, plan_class = f"VAN-{row['student_class']}", None
        cursor = conn.execute(
            "INSERT INTO fee_plan (academic_year_id, code, fee_type, student_class, category, annual_amount_paise,"
            " is_default, is_active, description, inserted_on, updated_on) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?)",
            (row["academic_year_id"], code, row["fee_type"], plan_class, annual,
             int(row["is_active"] and row["fee_type"] == "TUITION"), row["is_active"],
             "Converted from the monthly fee structure", stamp, stamp))
        plan_ids[(row["academic_year_id"], row["student_class"], row["fee_type"])] = (cursor.lastrowid, annual)
        log(f"Plan {code}: annual {annual / 100:,.2f}")

    # ---- dues: merge monthly rows into one annual due per enrollment and type
    new_id_for = {}
    groups = defaultdict(list)
    for due in conn.execute(
            "SELECT d.*, e.academic_year_id, e.student_class FROM student_fee_due d"
            " JOIN student_enrollment e ON e.id = d.enrollment_id ORDER BY d.id").fetchall():
        if due["fee_month"] is None:
            conn.execute(
                "INSERT INTO student_fee_due_v4 (id, enrollment_id, fee_type, fee_plan_id, description, override_reason,"
                " amount_due_paise, inserted_on, updated_on) VALUES (?, ?, ?, NULL, ?, NULL, ?, ?, ?)",
                (due["id"], due["enrollment_id"], due["fee_type"], due["description"], due["amount_due_paise"],
                 due["inserted_on"], due["updated_on"]))
            new_id_for[due["id"]] = due["id"]
        else:
            groups[(due["enrollment_id"], due["fee_type"])].append(due)

    for (enrollment_id, fee_type), dues in groups.items():
        first = dues[0]
        total = sum(d["amount_due_paise"] for d in dues)
        plan = plan_ids.get((first["academic_year_id"], first["student_class"], fee_type))
        plan_id = plan[0] if plan and plan[1] == total else None
        conn.execute(
            "INSERT INTO student_fee_due_v4 (id, enrollment_id, fee_type, fee_plan_id, description, override_reason,"
            " amount_due_paise, inserted_on, updated_on) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?)",
            (first["id"], enrollment_id, fee_type, plan_id, None if plan_id else CONVERTED_REASON, total,
             first["inserted_on"], stamp))
        for due in dues:
            new_id_for[due["id"]] = first["id"]
    log(f"Merged monthly dues into {len(groups)} annual dues")

    # ---- allocations: re-point and merge (one row per payment and due)
    merged = defaultdict(int)
    for row in conn.execute("SELECT payment_id, fee_due_id, amount_paise FROM payment_allocation ORDER BY id"):
        merged[(row["payment_id"], new_id_for[row["fee_due_id"]])] += row["amount_paise"]
    for (payment_id, fee_due_id), amount in sorted(merged.items()):
        conn.execute("INSERT INTO payment_allocation_v4 (payment_id, fee_due_id, amount_paise) VALUES (?, ?, ?)",
                     (payment_id, fee_due_id, amount))

    conn.execute("DROP TABLE payment_allocation")
    conn.execute("DROP TABLE student_fee_due")
    conn.execute("DROP TABLE fee_structure")
    conn.execute("ALTER TABLE student_fee_due_v4 RENAME TO student_fee_due")
    conn.execute("ALTER TABLE payment_allocation_v4 RENAME TO payment_allocation")
    execute_script(conn, FINAL_OBJECTS_SQL)

    # ---- reconciliation: every enrollment keeps exactly the same totals
    if _balances(conn) != balances_before:
        raise MigrationError("Reconciliation failed: balances changed while converting monthly fees")
    if _scalar(conn, "SELECT SUM(amount_paise) FROM payment_allocation") != allocated_before:
        raise MigrationError("Reconciliation failed: allocated amounts changed")
    log(f"Reconciled {len(balances_before)} enrollments; balances unchanged")
    log("No payment milestones set yet: until an admin adds them, fees count as overdue only after the term ends")
