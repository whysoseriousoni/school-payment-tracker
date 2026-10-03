"""
Fixed lists and enumerations used across the application.

Enums subclass `str` so they compare equal to the plain strings stored in
SQLite and render cleanly in Streamlit widgets.
"""
from enum import Enum

# Promotion order matters: a student moves to the next entry in this list.
CLASSES = ["LKG", "UKG", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]

SECTIONS = ["A", "B"]

# DG = Disadvantaged Group (reservation quota). Informational / reporting only.
STUDENT_CATEGORY = ["MANAGEMENT", "DG 1", "DG 2"]

USER_IDENTIFIER_TYPES = ["AADHAR"]

GUARDIAN_TYPES = ["MOTHER", "FATHER", "GUARDIAN", "BROTHER", "SISTER", "COUSIN", "RELATIVE", "DRIVER"]

PAYMENT_METHODS = ["CASH", "UPI", "CARD"]

# Fee months of the school operation year, in order.
FEE_MONTH_NAMES = ["Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May"]


class FeeType(str, Enum):
    TUITION = "TUITION"
    VAN = "VAN"
    BOOK = "BOOK"
    UNIFORM = "UNIFORM"
    PETROL = "PETROL"
    CUSTOM = "CUSTOM"

    @property
    def label(self) -> str:
        return FEE_TYPE_LABELS[self]

    @property
    def is_recurring(self) -> bool:
        return self in RECURRING_FEE_TYPES


FEE_TYPE_LABELS = {
    FeeType.TUITION: "Tuition Fee",
    FeeType.VAN: "Van Fee",
    FeeType.BOOK: "Book Fee",
    FeeType.UNIFORM: "Uniform Fee",
    FeeType.PETROL: "Petrol Fee",
    FeeType.CUSTOM: "Custom Fee",
}

# Recurring fees create one due row per month (Jun -> May). Must match the
# CHECK constraint on student_fee_due in migration 001.
RECURRING_FEE_TYPES = (FeeType.TUITION, FeeType.VAN)
ONE_OFF_FEE_TYPES = tuple(fee_type for fee_type in FeeType if fee_type not in RECURRING_FEE_TYPES)


class StudentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    LEFT = "LEFT"
    PASSED_OUT = "PASSED_OUT"


class EnrollmentOutcome(str, Enum):
    PROMOTED = "PROMOTED"
    RETAINED = "RETAINED"
    LEFT = "LEFT"
    PASSED_OUT = "PASSED_OUT"


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    BILLER = "BILLER"
