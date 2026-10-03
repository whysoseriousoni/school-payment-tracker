import sqlite3

import pytest

from data_management.migrations import MIGRATIONS
from data_management.migrations.runner import MigrationError, run_pending_migrations

LATEST_VERSION = MIGRATIONS[-1].VERSION


def _versions(conn):
    return [row[0] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]


def test_fresh_database_gets_full_schema_without_backup(fresh_db, connect, tmp_path):
    conn = connect(fresh_db)
    assert _versions(conn) == [module.VERSION for module in MIGRATIONS]
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"student", "student_enrollment", "student_fee_due", "payment", "payment_allocation"} <= tables
    assert not any(name.startswith("legacy_") for name in tables)
    assert not (tmp_path / "backups").exists(), "an empty new database needs no backup"


def test_rerun_is_a_no_op(migrated_db, tmp_path):
    assert run_pending_migrations(db_path=migrated_db, backup_dir=tmp_path / "backups") == []


def test_backup_taken_before_migrating_existing_data(migrated_db, tmp_path):
    backups = list((tmp_path / "backups").glob("*pre_migration_v001*.db"))
    assert len(backups) == 1
    snapshot = sqlite3.connect(backups[0])
    assert snapshot.execute("SELECT COUNT(*) FROM billing_details").fetchone()[0] == 3
    snapshot.close()


def test_students_imported_with_placeholders(migrated_db, connect):
    conn = connect(migrated_db)
    students = {row["id"]: row for row in conn.execute("SELECT * FROM student")}
    assert len(students) == 6
    assert students[1]["name"] == "PRADEEP" and students[1]["admission_no"] == "ADM-00001"
    assert students[2]["name"] == "UNNAMED STUDENT #2" and "Name was missing" in students[2]["notes"]
    assert students[6]["category"] == "DG 1"
    assert students[2]["category"] is None
    last4 = conn.execute(
        "SELECT i.last_4_digits, i.ciphertext FROM student s JOIN identifier i ON i.id = s.identifier_id WHERE s.id = 1"
    ).fetchone()
    assert tuple(last4) == ("6004", None)


def test_enrollments_and_guardians(migrated_db, connect):
    conn = connect(migrated_db)
    year = conn.execute("SELECT * FROM academic_year WHERE is_current = 1").fetchone()
    assert (year["label"], year["start_date"], year["end_date"]) == ("2026-27", "2026-06-01", "2027-05-31")
    enrollments = conn.execute("SELECT student_class, section, roll_no FROM student_enrollment ORDER BY student_id").fetchall()
    assert [row["student_class"] for row in enrollments] == ["2", "3", "UKG", "4", "UKG", "UKG"]
    assert {row["section"] for row in enrollments} == {"A"}
    assert all(row["roll_no"] is None for row in enrollments)
    link = conn.execute("SELECT * FROM student_guardian").fetchone()
    assert (link["student_id"], link["guardian_id"], link["relation_type"], link["is_primary"]) == (1, 1, "MOTHER", 1)


def test_tuition_dues_and_payment_allocation(migrated_db, connect):
    conn = connect(migrated_db)
    assert conn.execute(
        "SELECT monthly_amount_paise FROM fee_structure WHERE student_class = '2' AND fee_type = 'TUITION'"
    ).fetchone()[0] == 250000

    ledger = conn.execute(
        "SELECT fee_month, amount_due_paise, amount_paid_paise, balance_paise FROM v_fee_due_status"
        " WHERE student_id = 1 ORDER BY fee_month"
    ).fetchall()
    assert len(ledger) == 12 and ledger[0]["fee_month"] == "2026-06-01" and ledger[-1]["fee_month"] == "2027-05-01"
    assert [row["amount_paid_paise"] for row in ledger[:5]] == [250000, 250000, 250000, 250000, 130000]
    assert sum(row["balance_paise"] for row in ledger) == 3000000 - 1130000

    # Students in classes without a fee structure get no dues yet.
    assert conn.execute(
        "SELECT COUNT(*) FROM student_fee_due d JOIN student_enrollment e ON e.id = d.enrollment_id WHERE e.student_id <> 1"
    ).fetchone()[0] == 0


def test_payments_have_receipts_and_reconcile(migrated_db, connect):
    conn = connect(migrated_db)
    payments = conn.execute("SELECT * FROM payment ORDER BY receipt_no").fetchall()
    assert [row["receipt_no"] for row in payments] == ["RCPT/2026-27/00001", "RCPT/2026-27/00002", "RCPT/2026-27/00003"]
    assert [row["amount_paise"] for row in payments] == [300000, 330000, 500000]
    assert payments[0]["amount_in_words"] == "Three Thousand Rupees Only"
    assert payments[2]["payment_notes"] == "Cash 5000" and payments[2]["billing_name"] == "ELumalai"
    assert conn.execute("SELECT last_number FROM receipt_counter").fetchone()[0] == 3
    total_allocated = conn.execute("SELECT SUM(amount_paise) FROM payment_allocation").fetchone()[0]
    assert total_allocated == 1130000


def test_unmatched_tuition_payment_becomes_one_off_due(prototype_db, tmp_path, connect):
    conn = sqlite3.connect(prototype_db)
    conn.execute(
        "INSERT INTO billing_details (STUDENT_ID, STUDENT_CLASS, PAID_ON, AMOUNT_PAID, PAYMENT_METHOD, BILLING_TYPE)"
        " VALUES (4, '4', '2026-08-01', 1500, 'UPI', 'Term Fee')"
    )
    conn.execute(
        "INSERT INTO billing_details (STUDENT_ID, STUDENT_CLASS, PAID_ON, AMOUNT_PAID, PAYMENT_METHOD, BILLING_TYPE)"
        " VALUES (5, 'UKG', '2026-08-02', 700, 'CASH', 'Book Fee')"
    )
    conn.commit()
    conn.close()

    run_pending_migrations(db_path=prototype_db, backup_dir=tmp_path / "backups")
    dues = {
        row["fee_type"]: row
        for row in connect(prototype_db).execute("SELECT * FROM v_fee_due_status WHERE fee_month IS NULL")
    }
    assert dues["CUSTOM"]["student_id"] == 4 and dues["CUSTOM"]["amount_paid_paise"] == 150000
    assert dues["BOOK"]["student_id"] == 5 and dues["BOOK"]["balance_paise"] == 0


def test_failed_migration_rolls_back_completely(prototype_db, tmp_path, connect):
    conn = sqlite3.connect(prototype_db)
    conn.execute("INSERT INTO billing_details (STUDENT_ID, PAID_ON, AMOUNT_PAID) VALUES (999, '2026-07-01', 100)")
    conn.commit()
    conn.close()

    with pytest.raises(MigrationError, match="missing student 999"):
        run_pending_migrations(db_path=prototype_db, backup_dir=tmp_path / "backups")

    check = connect(prototype_db)
    assert _versions(check) == [1], "001 committed, 002 rolled back"
    assert check.execute("SELECT COUNT(*) FROM student").fetchone()[0] == 0
    assert check.execute("SELECT COUNT(*) FROM legacy_billing_details").fetchone()[0] == 4

    # Fix the bad row and the next start completes the upgrade.
    check.execute("DELETE FROM legacy_billing_details WHERE STUDENT_ID = 999")
    check.commit()
    applied = run_pending_migrations(db_path=prototype_db, backup_dir=tmp_path / "backups")
    assert [migration.version for migration in applied] == [2, 3]
    assert check.execute("SELECT COUNT(*) FROM payment").fetchone()[0] == 3
