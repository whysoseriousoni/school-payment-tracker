"""
Migration 002 - import data from the prototype (legacy_*) tables.

Rules applied:
  * Student and guardian IDs are preserved.
  * Every student is enrolled in the current academic year in section 'A'
    (roll numbers left empty to be assigned), plus any year a bill falls in.
  * Yearly fee structures become monthly tuition (annual / 12), and 12 tuition
    dues (Jun -> May) are generated for enrollments in classes that have one.
  * Each prototype bill becomes a payment with a receipt number, allocated to
    the oldest unpaid month first. Anything that cannot be matched to a due is
    recorded as a one-off due, so every rupee stays visible.
  * The migration aborts unless total money in == total money out.

Constants are frozen here on purpose: later changes to statics.py must not
change what this historical migration does.
"""
import json
import re
import sqlite3
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from config.settings import RECEIPT_PREFIX
from data_management.migrations.runner import LogFn, MigrationError
from helper.clock import now_ist
from helper.money import amount_in_words_inr, format_inr, rupees_to_paise
from helper.school_calendar import (
    academic_year_bounds,
    academic_year_label,
    academic_year_start_for,
    fee_months,
)

VERSION = 2
NAME = "import prototype data"

VALID_CLASSES = ["LKG", "UKG", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]
VALID_CATEGORIES = ["MANAGEMENT", "DG 1", "DG 2"]
DEFAULT_SECTION = "A"
DEFAULT_RELATION = "GUARDIAN"
IMPORTED_BY = "prototype-import"

LEGACY_FEE_TYPES = {
    "term fee": "TUITION",
    "tuition fee": "TUITION",
    "van fee": "VAN",
    "uniform fee": "UNIFORM",
    "book fee": "BOOK",
    "petrol fee": "PETROL",
}
RECURRING = ("TUITION", "VAN")

_DT_FORMAT = "%Y-%m-%d %H:%M:%S.%f"


# ---------- small parsing helpers ----------

def _parse_datetime(value: object) -> Optional[datetime]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    for pattern in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:26], pattern)
        except ValueError:
            continue
    return None


def _parse_date(value: object) -> Optional[date]:
    parsed = _parse_datetime(value)
    return parsed.date() if parsed else None


def _date_text(value: Optional[date]) -> Optional[str]:
    return value.isoformat() if value else None


def _stamp(value: object, fallback: str) -> str:
    parsed = _parse_datetime(value)
    return parsed.strftime(_DT_FORMAT) if parsed else fallback


def _clean(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone() is not None


def _rows(conn: sqlite3.Connection, table: str, order_by: str = "ID") -> List[sqlite3.Row]:
    if not _table_exists(conn, table):
        return []
    return conn.execute(f'SELECT * FROM "{table}" ORDER BY {order_by}').fetchall()


# ---------- migration steps ----------

def _create_academic_years(conn, year_starts, current_start, stamp, log) -> Dict[int, int]:
    year_ids = {}
    for start_year in sorted(year_starts):
        start, end = academic_year_bounds(start_year)
        cursor = conn.execute(
            "INSERT INTO academic_year (label, start_date, end_date, is_current, inserted_on, updated_on)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (academic_year_label(start_year), start.isoformat(), end.isoformat(),
             int(start_year == current_start), stamp, stamp),
        )
        year_ids[start_year] = cursor.lastrowid
        log(f"Created academic year {academic_year_label(start_year)}"
            + (" (current)" if start_year == current_start else ""))
    return year_ids


def _import_students(conn, legacy_students, stamp, log) -> Dict[int, Optional[str]]:
    """Returns {student_id: current_class or None when the class is unusable}."""
    current_classes = {}
    for row in legacy_students:
        student_id = row["ID"]
        notes = []

        name = _clean(row["NAME"])
        if not name:
            name = f"UNNAMED STUDENT #{student_id}"
            notes.append("Name was missing in the prototype data - correct or remove this record.")
            log(f"Student {student_id}: name missing, saved as '{name}'")

        identifier_id = None
        last_4 = _clean(row["LAST_4_DIGIT_OF_IDENTIFIER"])
        if last_4 and re.fullmatch(r"\d{4}", last_4):
            cursor = conn.execute(
                "INSERT INTO identifier (identifier_type, ciphertext, nonce, last_4_digits, key_version,"
                " inserted_on, updated_on) VALUES (?, NULL, NULL, ?, 1, ?, ?)",
                (_clean(row["IDENTIFIER_TYPE"]) or "AADHAR", last_4, stamp, stamp),
            )
            identifier_id = cursor.lastrowid
        elif last_4:
            notes.append(f"Invalid identifier last 4 digits '{last_4}' were not imported.")
            log(f"Student {student_id}: invalid identifier last-4 '{last_4}' dropped")

        category = _clean(row["CATEGORY"])
        if category and category not in VALID_CATEGORIES:
            notes.append(f"Unknown category '{category}' was not imported.")
            log(f"Student {student_id}: unknown category '{category}' dropped")
            category = None

        class_joined = _clean(row["CLASS_JOINED"])
        if class_joined not in VALID_CLASSES:
            class_joined = None

        current_class = _clean(row["CURRENT_CLASS"])
        if current_class not in VALID_CLASSES:
            notes.append(f"Current class '{current_class}' was not recognised; enroll this student manually.")
            log(f"Student {student_id}: unrecognised class '{current_class}', not enrolled")
            current_class = None
        current_classes[student_id] = current_class

        conn.execute(
            "INSERT INTO student (id, admission_no, name, date_of_birth, category, status, date_of_join,"
            " class_joined, date_of_leaving, identifier_id, notes, inserted_on, updated_on)"
            " VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?, NULL, ?, ?, ?, ?)",
            (
                student_id,
                f"ADM-{student_id:05d}",
                name,
                _date_text(_parse_date(row["DATE_OF_BIRTH"])),
                category,
                _date_text(_parse_date(row["DATE_OF_JOIN"])),
                class_joined,
                identifier_id,
                " ".join(notes) or None,
                _stamp(row["INSERTED_ON"], stamp),
                _stamp(row["LAST_UPDATED"], stamp),
            ),
        )
    log(f"Imported {len(legacy_students)} students (admission numbers ADM-xxxxx are placeholders)")
    return current_classes


def _import_guardians(conn, legacy_guardians, student_ids, stamp, log) -> None:
    has_primary = set()
    for row in legacy_guardians:
        guardian_id = row["ID"]
        name = _clean(row["NAME"]) or f"UNNAMED GUARDIAN #{guardian_id}"
        conn.execute(
            "INSERT INTO guardian (id, name, mobile_number, year_of_birth, inserted_on, updated_on)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (guardian_id, name, _clean(row["MOBILE_NUMBER"]), row["YEAR_OF_BIRTH"], stamp, stamp),
        )

        linked = set()
        if row["STUDENT_ID"] is not None:
            linked.add(int(row["STUDENT_ID"]))
        blob = row["STUDENT_IDS"]
        if blob:
            try:
                text = blob.decode("utf-8") if isinstance(blob, bytes) else str(blob)
                linked.update(int(value) for value in json.loads(text))
            except (ValueError, TypeError):
                log(f"Guardian {guardian_id}: could not read STUDENT_IDS {blob!r}")

        for student_id in sorted(linked):
            if student_id not in student_ids:
                log(f"Guardian {guardian_id}: student {student_id} does not exist, link skipped")
                continue
            is_primary = int(student_id not in has_primary)
            conn.execute(
                "INSERT INTO student_guardian (student_id, guardian_id, relation_type, is_primary,"
                " inserted_on, updated_on) VALUES (?, ?, ?, ?, ?, ?)",
                (student_id, guardian_id, _clean(row["RELATION_TYPE"]) or DEFAULT_RELATION, is_primary, stamp, stamp),
            )
            has_primary.add(student_id)
    log(f"Imported {len(legacy_guardians)} guardians with student links")


def _import_fee_structures(conn, legacy_fees, year_ids, stamp, log) -> Dict[Tuple[int, str], int]:
    """Returns {(year_start, class): monthly tuition paise} for active structures."""
    monthly_tuition = {}
    for row in legacy_fees:
        student_class = _clean(row["STUDENT_CLASS"])
        start = _parse_date(row["START_DATE"])
        if student_class not in VALID_CLASSES or start is None:
            log(f"Fee structure {row['ID']}: invalid class/start date, skipped")
            continue
        year_start = academic_year_start_for(start)
        key = (year_start, student_class)
        if key in monthly_tuition:
            log(f"Fee structure {row['ID']}: duplicate for class {student_class}, skipped")
            continue

        annual_paise = rupees_to_paise(row["AMOUNT_TO_PAY"] or 0)
        monthly_paise, remainder = divmod(annual_paise, 12)
        if remainder:
            log(f"Fee structure class {student_class}: {format_inr(annual_paise)} is not divisible by 12; "
                f"monthly set to {format_inr(monthly_paise)}")
        is_active = int(bool(row["IS_ACTIVE"]))
        conn.execute(
            "INSERT INTO fee_structure (academic_year_id, student_class, fee_type, monthly_amount_paise,"
            " is_active, inserted_on, updated_on) VALUES (?, ?, 'TUITION', ?, ?, ?, ?)",
            (year_ids[year_start], student_class, monthly_paise, is_active,
             _stamp(row["INSERTED_ON"], stamp), _stamp(row["UPDATED_ON"], stamp)),
        )
        if is_active:
            monthly_tuition[key] = monthly_paise
        log(f"Fee structure {academic_year_label(year_start)} class {student_class}: "
            f"tuition {format_inr(monthly_paise)} / month")
    return monthly_tuition


def _per_student_tuition_overrides(legacy_annual_fees) -> Dict[Tuple[int, int], int]:
    """{(student_id, year_start): monthly paise} from the prototype student_annual_fee table."""
    overrides = {}
    for row in legacy_annual_fees:
        start = _parse_date(row["PAYMENT_START_DATE"])
        if start is None or row["FEE_AMOUNT"] is None or row["STUDENT_ID"] is None:
            continue
        overrides[(int(row["STUDENT_ID"]), academic_year_start_for(start))] = rupees_to_paise(row["FEE_AMOUNT"]) // 12
    return overrides


def _create_enrollments_and_dues(conn, needed, current_classes, bill_classes, year_ids,
                                 monthly_tuition, overrides, stamp, log) -> Dict[Tuple[int, int], int]:
    enrollment_ids = {}
    for student_id, year_start in sorted(needed):
        student_class = bill_classes.get((student_id, year_start)) or current_classes.get(student_id)
        if student_class is None:
            continue
        cursor = conn.execute(
            "INSERT INTO student_enrollment (student_id, academic_year_id, student_class, section, roll_no,"
            " outcome, inserted_on, updated_on) VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)",
            (student_id, year_ids[year_start], student_class, DEFAULT_SECTION, stamp, stamp),
        )
        enrollment_id = cursor.lastrowid
        enrollment_ids[(student_id, year_start)] = enrollment_id

        monthly = monthly_tuition.get((year_start, student_class))
        override = overrides.get((student_id, year_start))
        if override is not None and override != monthly:
            log(f"Student {student_id}: individual tuition {format_inr(override)} / month used")
            monthly = override
        if monthly is None:
            continue
        for month in fee_months(year_start):
            conn.execute(
                "INSERT INTO student_fee_due (enrollment_id, fee_type, fee_month, description, amount_due_paise,"
                " inserted_on, updated_on) VALUES (?, 'TUITION', ?, NULL, ?, ?, ?)",
                (enrollment_id, month.isoformat(), monthly, stamp, stamp),
            )
    log(f"Created {len(enrollment_ids)} enrollments in section {DEFAULT_SECTION} (roll numbers to be assigned)")
    return enrollment_ids


def _insert_one_off_due(conn, enrollment_id, fee_type, description, amount_paise, stamp) -> int:
    cursor = conn.execute(
        "INSERT INTO student_fee_due (enrollment_id, fee_type, fee_month, description, amount_due_paise,"
        " inserted_on, updated_on) VALUES (?, ?, NULL, ?, ?, ?, ?)",
        (enrollment_id, fee_type, description, amount_paise, stamp, stamp),
    )
    return cursor.lastrowid


def _allocate(conn, payment_id, fee_due_id, amount_paise) -> None:
    conn.execute(
        "INSERT INTO payment_allocation (payment_id, fee_due_id, amount_paise) VALUES (?, ?, ?)",
        (payment_id, fee_due_id, amount_paise),
    )


def _import_bills(conn, bills, enrollment_ids, year_ids, stamp, log) -> int:
    """Returns total paise imported."""
    counters: Dict[int, int] = {}
    paid_so_far: Dict[int, int] = {}  # fee_due_id -> allocated paise
    total = 0

    for row, paid_on in bills:
        amount = rupees_to_paise(row["AMOUNT_PAID"] or 0)
        student_id = int(row["STUDENT_ID"])
        year_start = academic_year_start_for(paid_on)
        enrollment_id = enrollment_ids.get((student_id, year_start))
        if enrollment_id is None:
            raise MigrationError(
                f"Bill {row['ID']}: student {student_id} has no usable class for "
                f"{academic_year_label(year_start)}; fix the prototype row and restart"
            )

        counters[year_start] = counters.get(year_start, 0) + 1
        receipt_no = f"{RECEIPT_PREFIX}/{academic_year_label(year_start)}/{counters[year_start]:05d}"

        raw_type = _clean(row["BILLING_TYPE"])
        fee_type = LEGACY_FEE_TYPES.get((raw_type or "").lower())
        if raw_type is None:
            fee_type = "TUITION"
            log(f"Bill {row['ID']}: no billing type, treated as tuition")
        elif fee_type is None:
            fee_type = "CUSTOM"

        cursor = conn.execute(
            "INSERT INTO payment (receipt_no, student_id, enrollment_id, paid_on, amount_paise, payment_method,"
            " payment_notes, billing_name, notes, amount_in_words, collected_by, is_voided, inserted_on, updated_on)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
            (
                receipt_no, student_id, enrollment_id, paid_on.isoformat(), amount,
                _clean(row["PAYMENT_METHOD"]) or "CASH", _clean(row["PAYMENT_NOTES"]),
                _clean(row["BILLING_NAME"]), _clean(row["NOTES"]), amount_in_words_inr(amount), IMPORTED_BY,
                _stamp(row["INSERTED_ON"], stamp), _stamp(row["UPDATED_ON"], stamp),
            ),
        )
        payment_id = cursor.lastrowid
        total += amount

        remaining = amount
        covered = []
        if fee_type in RECURRING:
            dues = conn.execute(
                "SELECT id, fee_month, amount_due_paise FROM student_fee_due"
                " WHERE enrollment_id = ? AND fee_type = ? ORDER BY fee_month",
                (enrollment_id, fee_type),
            ).fetchall()
            for due in dues:
                if remaining == 0:
                    break
                open_amount = due["amount_due_paise"] - paid_so_far.get(due["id"], 0)
                if open_amount <= 0:
                    continue
                portion = min(open_amount, remaining)
                _allocate(conn, payment_id, due["id"], portion)
                paid_so_far[due["id"]] = paid_so_far.get(due["id"], 0) + portion
                remaining -= portion
                covered.append(datetime.strptime(due["fee_month"], "%Y-%m-%d").strftime("%b"))

        if remaining > 0:
            description = (
                f"Prototype {raw_type or 'tuition'} payment not covered by a fee structure"
                if fee_type in RECURRING else (raw_type or fee_type.title())
            )
            due_type = "CUSTOM" if fee_type in RECURRING else fee_type
            due_id = _insert_one_off_due(conn, enrollment_id, due_type, description, remaining, stamp)
            _allocate(conn, payment_id, due_id, remaining)
            covered.append(f"one-off '{description}'")

        log(f"Bill {row['ID']} -> {receipt_no}: {format_inr(amount)} applied to {', '.join(covered)}")

    for year_start, last_number in counters.items():
        conn.execute(
            "INSERT INTO receipt_counter (academic_year_id, last_number) VALUES (?, ?)",
            (year_ids[year_start], last_number),
        )
    return total


def _scalar(conn, sql: str) -> int:
    return conn.execute(sql).fetchone()[0] or 0


def upgrade(conn: sqlite3.Connection, log: LogFn) -> None:
    if not _table_exists(conn, "legacy_student"):
        log("No prototype data found; nothing to import")
        return

    now = now_ist()
    stamp = now.strftime(_DT_FORMAT)
    current_start = academic_year_start_for(now.date())

    legacy_students = _rows(conn, "legacy_student")
    student_ids = {row["ID"] for row in legacy_students}

    bills = []
    for row in _rows(conn, "legacy_billing_details"):
        if rupees_to_paise(row["AMOUNT_PAID"] or 0) <= 0:
            log(f"Bill {row['ID']}: zero amount, skipped")
            continue
        if row["STUDENT_ID"] is None or int(row["STUDENT_ID"]) not in student_ids:
            raise MigrationError(f"Bill {row['ID']} refers to missing student {row['STUDENT_ID']}")
        paid_on = _parse_date(row["PAID_ON"]) or _parse_date(row["INSERTED_ON"])
        if paid_on is None:
            raise MigrationError(f"Bill {row['ID']} has no usable payment date")
        bills.append((row, paid_on))
    bills.sort(key=lambda item: (item[1], item[0]["ID"]))

    legacy_fees = _rows(conn, "legacy_fee_structure_yearly")
    year_starts = {current_start}
    year_starts.update(academic_year_start_for(paid_on) for _, paid_on in bills)
    year_starts.update(
        academic_year_start_for(start)
        for start in (_parse_date(row["START_DATE"]) for row in legacy_fees)
        if start is not None
    )

    year_ids = _create_academic_years(conn, year_starts, current_start, stamp, log)
    current_classes = _import_students(conn, legacy_students, stamp, log)
    _import_guardians(conn, _rows(conn, "legacy_guardian_details"), student_ids, stamp, log)
    monthly_tuition = _import_fee_structures(conn, legacy_fees, year_ids, stamp, log)
    overrides = _per_student_tuition_overrides(_rows(conn, "legacy_student_annual_fee"))

    bill_classes = {}
    for row, paid_on in bills:
        bill_class = _clean(row["STUDENT_CLASS"])
        if bill_class in VALID_CLASSES:
            bill_classes.setdefault((int(row["STUDENT_ID"]), academic_year_start_for(paid_on)), bill_class)
    needed = {(student_id, current_start) for student_id in student_ids}
    needed.update((int(row["STUDENT_ID"]), academic_year_start_for(paid_on)) for row, paid_on in bills)

    enrollment_ids = _create_enrollments_and_dues(
        conn, needed, current_classes, bill_classes, year_ids, monthly_tuition, overrides, stamp, log
    )

    legacy_ciphertexts = [row for row in _rows(conn, "legacy_identifier_table") if row["IDENTIFIER_VALUE_AES"]]
    if legacy_ciphertexts:
        log(f"{len(legacy_ciphertexts)} prototype encrypted identifiers were not imported "
            "(unknown key/format); only last 4 digits were kept - re-enter full numbers")

    imported_total = _import_bills(conn, bills, enrollment_ids, year_ids, stamp, log)

    # ---------- reconciliation: refuse to commit if any money is unaccounted for ----------
    expected = sum(rupees_to_paise(row["AMOUNT_PAID"]) for row, _ in bills)
    paid = _scalar(conn, "SELECT SUM(amount_paise) FROM payment")
    allocated = _scalar(conn, "SELECT SUM(amount_paise) FROM payment_allocation")
    if not expected == imported_total == paid == allocated:
        raise MigrationError(
            f"Reconciliation failed: prototype={expected}, imported={imported_total}, "
            f"payments={paid}, allocations={allocated} (paise)"
        )
    if _scalar(conn, "SELECT COUNT(*) FROM student") != len(legacy_students):
        raise MigrationError("Reconciliation failed: student count mismatch")
    log(f"Reconciled: {len(bills)} bills, {format_inr(expected)} fully allocated")
    log("Prototype tables kept as legacy_* for reference; a later migration can drop them")
