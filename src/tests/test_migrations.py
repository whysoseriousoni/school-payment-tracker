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


def test_monthly_fees_converted_to_annual_plan(migrated_db, connect):
    conn = connect(migrated_db)
    plan = conn.execute("SELECT * FROM fee_plan").fetchone()
    assert (plan["code"], plan["fee_type"], plan["student_class"], plan["annual_amount_paise"], plan["is_default"]) == \
        ("2-FEE-1", "TUITION", "2", 3000000, 1)
    dues = conn.execute("SELECT * FROM v_fee_due_status").fetchall()
    assert len(dues) == 1
    tuition = dues[0]
    assert (tuition["student_id"], tuition["plan_code"], tuition["amount_due_paise"], tuition["amount_paid_paise"],
            tuition["balance_paise"]) == (1, "2-FEE-1", 3000000, 1130000, 1870000)
    allocations = conn.execute("SELECT payment_id, amount_paise FROM payment_allocation ORDER BY payment_id").fetchall()
    assert [tuple(a) for a in allocations] == [(1, 300000), (2, 330000), (3, 500000)]  # merged: one row per receipt
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "fee_structure" not in tables and {"fee_plan", "fee_milestone"} <= tables


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
        for row in connect(prototype_db).execute(
            "SELECT * FROM v_fee_due_status WHERE fee_type NOT IN ('TUITION', 'VAN')")
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
    assert [migration.version for migration in applied] == [2, 3, 4]
    assert check.execute("SELECT COUNT(*) FROM payment").fetchone()[0] == 3


def test_monthly_v3_data_converts_without_changing_any_balance(tmp_path, monkeypatch, connect):
    """A database used with the monthly version (van, part payments, a voided receipt) upgrades exactly."""
    import data_management.migrations as registry
    from data_management.migrations import m004_fee_plans_and_flexible_payment as m004

    path = tmp_path / "v3.db"
    monkeypatch.setattr(registry, "MIGRATIONS", registry.MIGRATIONS[:3])
    run_pending_migrations(db_path=path, backup_dir=tmp_path / "b")
    stamp = "2026-07-01 10:00:00.000000"
    conn = connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(f"""
        INSERT INTO academic_year VALUES (1, '2026-27', '2026-06-01', '2027-05-31', 1, '{stamp}', '{stamp}');
        INSERT INTO student (id, admission_no, name, status, inserted_on, updated_on)
            VALUES (1, 'A1', 'Asha', 'ACTIVE', '{stamp}', '{stamp}'), (2, 'A2', 'Ravi', 'ACTIVE', '{stamp}', '{stamp}');
        INSERT INTO student_enrollment (id, student_id, academic_year_id, student_class, section, inserted_on, updated_on)
            VALUES (1, 1, 1, 'LKG', 'A', '{stamp}', '{stamp}'), (2, 2, 1, 'LKG', 'A', '{stamp}', '{stamp}');
        INSERT INTO fee_structure (academic_year_id, student_class, fee_type, monthly_amount_paise, is_active,
                                   inserted_on, updated_on) VALUES (1, 'LKG', 'TUITION', 200000, 1, '{stamp}', '{stamp}');
    """)
    months = ["2026-06-01", "2026-07-01", "2026-08-01", "2026-09-01", "2026-10-01", "2026-11-01",
              "2026-12-01", "2027-01-01", "2027-02-01", "2027-03-01", "2027-04-01", "2027-05-01"]
    for enrollment in (1, 2):
        for month in months:  # student 2 joined late: no June/July tuition -> custom annual amount
            if enrollment == 2 and month in months[:2]:
                continue
            conn.execute("INSERT INTO student_fee_due (enrollment_id, fee_type, fee_month, amount_due_paise, inserted_on,"
                         " updated_on) VALUES (?, 'TUITION', ?, 200000, ?, ?)", (enrollment, month, stamp, stamp))
    for month in months[3:]:
        conn.execute("INSERT INTO student_fee_due (enrollment_id, fee_type, fee_month, amount_due_paise, inserted_on,"
                     " updated_on) VALUES (1, 'VAN', ?, 70000, ?, ?)", (month, stamp, stamp))
    conn.execute("INSERT INTO student_fee_due (enrollment_id, fee_type, description, amount_due_paise, inserted_on,"
                 " updated_on) VALUES (1, 'BOOK', 'Books', 150000, ?, ?)", (stamp, stamp))

    def pay(receipt, enrollment, student, allocations, voided=False):
        payment_id = conn.execute(
            "INSERT INTO payment (receipt_no, student_id, enrollment_id, paid_on, amount_paise, payment_method,"
            " amount_in_words, inserted_on, updated_on) VALUES (?, ?, ?, '2026-09-01', ?, 'CASH', 'x', ?, ?)",
            (receipt, student, enrollment, sum(a for _, a in allocations), stamp, stamp)).lastrowid
        for due_id, amount in allocations:
            conn.execute("INSERT INTO payment_allocation (payment_id, fee_due_id, amount_paise) VALUES (?, ?, ?)",
                         (payment_id, due_id, amount))
        if voided:
            conn.execute("UPDATE payment SET is_voided = 1, void_reason = 'mistake' WHERE id = ?", (payment_id,))

    due = lambda e, t, m=None: conn.execute(  # noqa: E731
        "SELECT id FROM student_fee_due WHERE enrollment_id = ? AND fee_type = ? AND fee_month IS ?", (e, t, m)
    ).fetchone()[0]
    pay("R1", 1, 1, [(due(1, "TUITION", months[0]), 200000), (due(1, "TUITION", months[1]), 200000),
                     (due(1, "TUITION", months[2]), 50000), (due(1, "VAN", months[3]), 70000)])
    pay("R2", 1, 1, [(due(1, "TUITION", months[2]), 150000), (due(1, "BOOK"), 150000)])
    pay("R3", 1, 1, [(due(1, "TUITION", months[3]), 200000)], voided=True)
    pay("R4", 2, 2, [(due(2, "TUITION", months[2]), 120000)])
    conn.commit()
    before = {r[0]: tuple(r[1:]) for r in conn.execute(
        "SELECT enrollment_id, SUM(amount_due_paise), SUM(amount_paid_paise) FROM v_fee_due_status GROUP BY 1")}

    monkeypatch.setattr(registry, "MIGRATIONS", registry.MIGRATIONS + [m004])
    run_pending_migrations(db_path=path, backup_dir=tmp_path / "b")
    after = {r[0]: tuple(r[1:]) for r in conn.execute(
        "SELECT enrollment_id, SUM(amount_due_paise), SUM(amount_paid_paise) FROM v_fee_due_status GROUP BY 1")}
    assert after == before
    dues = {(r["enrollment_id"], r["fee_type"]): r for r in conn.execute("SELECT * FROM v_fee_due_status")}
    assert (dues[(1, "TUITION")]["plan_code"], dues[(1, "TUITION")]["amount_due_paise"]) == ("LKG-FEE-1", 2400000)
    assert dues[(1, "TUITION")]["amount_paid_paise"] == 600000  # voided R3 not counted
    assert dues[(2, "TUITION")]["plan_code"] is None and dues[(2, "TUITION")]["override_reason"] == \
        "Converted from monthly fees" and dues[(2, "TUITION")]["amount_due_paise"] == 2000000
    assert (dues[(1, "VAN")]["amount_due_paise"], dues[(1, "VAN")]["override_reason"]) == (630000, "Converted from monthly fees")
    assert dues[(1, "BOOK")]["balance_paise"] == 0
    r1 = conn.execute("SELECT a.fee_due_id, a.amount_paise FROM payment_allocation a JOIN payment p ON p.id = a.payment_id"
                      " WHERE p.receipt_no = 'R1' ORDER BY a.amount_paise").fetchall()
    assert [r["amount_paise"] for r in r1] == [70000, 450000]  # tuition rows merged, van separate
    assert conn.execute("SELECT is_voided FROM payment WHERE receipt_no = 'R3'").fetchone()[0] == 1
