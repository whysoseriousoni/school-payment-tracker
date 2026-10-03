"""Table models must match the schema the migrations create, and round-trip through SQLModel."""
from datetime import date

import pytest
from sqlmodel import select

from data_management.dao import (
    AcademicYear,
    AppSetting,
    AppUser,
    FeeMilestone,
    FeePlan,
    Guardian,
    Identifier,
    Payment,
    PaymentAllocation,
    ReceiptCounter,
    Student,
    StudentEnrollment,
    StudentFeeDue,
    StudentGuardian,
)
from data_management.sql_manager import session_scope

MODELS = [AcademicYear, AppSetting, AppUser, FeeMilestone, FeePlan, Guardian, Identifier, Payment, PaymentAllocation,
          ReceiptCounter, Student, StudentEnrollment, StudentFeeDue, StudentGuardian]


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__name__)
def test_model_columns_match_database(model, fresh_db, connect):
    db_columns = {row["name"] for row in connect(fresh_db).execute(f"PRAGMA table_info({model.__tablename__})")}
    model_columns = {column.name for column in model.__table__.columns}
    assert db_columns, f"table {model.__tablename__} missing"
    assert model_columns == db_columns


def test_datetime_columns_are_naive(fresh_db):
    for model in MODELS:
        for column in model.__table__.columns:
            assert getattr(column.type, "timezone", False) is False, f"{model.__name__}.{column.name}"


def test_round_trip_and_foreign_keys(fresh_db):
    with session_scope(fresh_db) as session:
        year = AcademicYear(label="2026-27", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        student = Student(admission_no="ADM-1", name="Asha")
        session.add_all([year, student])
        session.flush()
        session.add(StudentEnrollment(student_id=student.id, academic_year_id=year.id, student_class="LKG", section="A"))

    with session_scope(fresh_db) as session:
        enrollment = session.exec(select(StudentEnrollment)).one()
        assert enrollment.student_class == "LKG"
        loaded = session.get(Student, enrollment.student_id)
        assert loaded.status == "ACTIVE" and loaded.inserted_on.tzinfo is None

    with pytest.raises(Exception):
        with session_scope(fresh_db) as session:
            session.add(StudentEnrollment(student_id=999, academic_year_id=1, student_class="1", section="A"))
