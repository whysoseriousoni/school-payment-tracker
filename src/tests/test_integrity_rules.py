"""The database itself must refuse invalid money operations, whatever the UI does."""
import sqlite3

import pytest

STAMP = "2026-10-01 10:00:00.000000"


def _payment(conn, receipt, enrollment_id, amount, student_id=1):
    return conn.execute(
        "INSERT INTO payment (receipt_no, student_id, enrollment_id, paid_on, amount_paise, payment_method,"
        " amount_in_words, inserted_on, updated_on) VALUES (?, ?, ?, '2026-10-01', ?, 'CASH', 'x', ?, ?)",
        (receipt, student_id, enrollment_id, amount, STAMP, STAMP),
    ).lastrowid


def _allocate(conn, payment_id, due_id, amount):
    conn.execute(
        "INSERT INTO payment_allocation (payment_id, fee_due_id, amount_paise) VALUES (?, ?, ?)",
        (payment_id, due_id, amount),
    )


@pytest.fixture
def db(migrated_db, connect):
    conn = connect(migrated_db)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _due(conn, month):
    return conn.execute(
        "SELECT fee_due_id, balance_paise FROM v_fee_due_status WHERE student_id = 1 AND fee_month = ?", (month,)
    ).fetchone()


def test_valid_allocation_is_accepted(db):
    due = _due(db, "2026-10-01")
    payment_id = _payment(db, "T-1", 1, due["balance_paise"])
    _allocate(db, payment_id, due["fee_due_id"], due["balance_paise"])
    assert _due(db, "2026-10-01")["balance_paise"] == 0


def test_cannot_overpay_a_due(db):
    due = _due(db, "2026-10-01")  # Rs 1,200 open
    payment_id = _payment(db, "T-2", 1, 500000)
    with pytest.raises(sqlite3.IntegrityError, match="exceed the amount due"):
        _allocate(db, payment_id, due["fee_due_id"], due["balance_paise"] + 1)


def test_cannot_allocate_more_than_payment(db):
    due = _due(db, "2026-11-01")
    payment_id = _payment(db, "T-3", 1, 1000)
    with pytest.raises(sqlite3.IntegrityError, match="exceed the payment amount"):
        _allocate(db, payment_id, due["fee_due_id"], 1001)


def test_no_carry_over_between_enrollments(db):
    other_enrollment = db.execute("SELECT id FROM student_enrollment WHERE student_id = 4").fetchone()[0]
    payment_id = _payment(db, "T-4", other_enrollment, 1000, student_id=4)
    with pytest.raises(sqlite3.IntegrityError, match="different enrollments"):
        _allocate(db, payment_id, _due(db, "2026-11-01")["fee_due_id"], 1000)


def test_void_frees_the_due_and_is_permanent(db):
    paid_month = _due(db, "2026-06-01")
    assert paid_month["balance_paise"] == 0
    db.execute("UPDATE payment SET is_voided = 1, void_reason = 'Entered twice' WHERE receipt_no = 'RCPT/2026-27/00001'")
    assert _due(db, "2026-06-01")["balance_paise"] == 250000
    with pytest.raises(sqlite3.IntegrityError, match="cannot be restored"):
        db.execute("UPDATE payment SET is_voided = 0 WHERE receipt_no = 'RCPT/2026-27/00001'")


def test_void_requires_reason(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE payment SET is_voided = 1 WHERE receipt_no = 'RCPT/2026-27/00002'")


def test_payments_cannot_be_deleted_or_altered(db):
    with pytest.raises(sqlite3.IntegrityError, match="void them instead"):
        db.execute("DELETE FROM payment WHERE id = 1")
    with pytest.raises(sqlite3.IntegrityError, match="cannot change"):
        db.execute("UPDATE payment SET amount_paise = 1 WHERE id = 1")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        db.execute("UPDATE payment_allocation SET amount_paise = 1 WHERE id = 1")


def test_due_cannot_drop_below_paid(db):
    june = _due(db, "2026-06-01")["fee_due_id"]
    with pytest.raises(sqlite3.IntegrityError, match="below the amount already paid"):
        db.execute("UPDATE student_fee_due SET amount_due_paise = 100 WHERE id = ?", (june,))


def test_structural_constraints(db):
    with pytest.raises(sqlite3.IntegrityError):  # recurring fee must have a month
        db.execute(
            "INSERT INTO student_fee_due (enrollment_id, fee_type, fee_month, amount_due_paise, inserted_on, updated_on)"
            " VALUES (1, 'TUITION', NULL, 100, ?, ?)", (STAMP, STAMP))
    with pytest.raises(sqlite3.IntegrityError):  # fee month must be the 1st
        db.execute(
            "INSERT INTO student_fee_due (enrollment_id, fee_type, fee_month, amount_due_paise, inserted_on, updated_on)"
            " VALUES (1, 'VAN', '2026-07-15', 100, ?, ?)", (STAMP, STAMP))
    with pytest.raises(sqlite3.IntegrityError):  # one enrollment per student per year
        db.execute(
            "INSERT INTO student_enrollment (student_id, academic_year_id, student_class, section, inserted_on, updated_on)"
            " VALUES (1, 1, '3', 'B', ?, ?)", (STAMP, STAMP))
    db.execute("UPDATE student_enrollment SET roll_no = 7 WHERE student_id = 3")
    with pytest.raises(sqlite3.IntegrityError):  # roll number unique within year/class/section
        db.execute("UPDATE student_enrollment SET roll_no = 7 WHERE student_id = 5")
    with pytest.raises(sqlite3.IntegrityError):  # only one current academic year
        db.execute(
            "INSERT INTO academic_year (label, start_date, end_date, is_current, inserted_on, updated_on)"
            " VALUES ('2027-28', '2027-06-01', '2028-05-31', 1, ?, ?)", (STAMP, STAMP))
    with pytest.raises(sqlite3.IntegrityError):  # enrollments block student deletion
        db.execute("DELETE FROM student WHERE id = 2")
