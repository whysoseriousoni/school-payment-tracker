"""
Table models (DAOs). Importing this package registers every table with
SQLModel metadata. The schema itself is created by the migrations.
"""
from data_management.dao.academic_year import AcademicYear
from data_management.dao.app_setting import AppSetting
from data_management.dao.app_user import AppUser
from data_management.dao.fee_structure import FeeStructure
from data_management.dao.guardian import Guardian
from data_management.dao.identifier import Identifier
from data_management.dao.payment import Payment
from data_management.dao.payment_allocation import PaymentAllocation
from data_management.dao.receipt_counter import ReceiptCounter
from data_management.dao.student import Student
from data_management.dao.student_enrollment import StudentEnrollment
from data_management.dao.student_fee_due import StudentFeeDue
from data_management.dao.student_guardian import StudentGuardian

__all__ = [
    "AcademicYear",
    "AppSetting",
    "AppUser",
    "FeeStructure",
    "Guardian",
    "Identifier",
    "Payment",
    "PaymentAllocation",
    "ReceiptCounter",
    "Student",
    "StudentEnrollment",
    "StudentFeeDue",
    "StudentGuardian",
]
