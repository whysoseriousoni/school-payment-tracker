from datetime import date
from io import BytesIO

import pytest
from openpyxl import load_workbook

from data_management.dto.fee import FeeStructureInput, OneOffDueCreate
from data_management.services import academic_year_service, fee_service, report_service
from data_management.services.report_service import ReportFilter
from helper.school_calendar import last_overdue_month
from reports.excel import build_workbook


@pytest.mark.parametrize("as_of, expected", [
    (date(2026, 10, 3), date(2026, 9, 1)), (date(2026, 10, 10), date(2026, 10, 1)),
    (date(2027, 1, 5), date(2026, 12, 1)), (date(2026, 6, 1), date(2026, 5, 1)),
])
def test_last_overdue_month(as_of, expected):
    assert last_overdue_month(as_of, 10) == expected


@pytest.fixture
def year(app_db):
    return academic_year_service.get_current_year()


def test_paid_up_until_october_falls_due(year):
    # Student 1 paid Jun-Sep in full and Rs 1,300 of October.
    early = report_service.student_balances(ReportFilter(year.id, as_of=date(2026, 10, 3)))
    student = early.set_index("enrollment_id").loc[1]
    assert student["payment_status"] == "Paid up" and student["overdue_paise"] == 0
    assert student["balance_paise"] == 1870000
    assert set(early["payment_status"]) == {"Paid up", "No fees set"}

    later = report_service.student_balances(ReportFilter(year.id, as_of=date(2026, 12, 15)))
    student = later.set_index("enrollment_id").loc[1]
    assert student["payment_status"] == "Defaulter"
    assert student["overdue_paise"] == 120000 + 250000 + 250000
    assert student["overdue_months"] == "Tuition Fee - Oct 2026, Tuition Fee - Nov 2026, Tuition Fee - Dec 2026"


def test_dashboard_and_defaulters(year):
    fee_service.save_structure(FeeStructureInput(academic_year_id=year.id, student_class="UKG", fee_type="TUITION",
                                                 monthly_amount_paise=100000))
    fee_service.apply_tuition_structure(year.id)
    enrollment_vbn = 6
    fee_service.add_one_off_due(OneOffDueCreate(enrollment_id=enrollment_vbn, fee_type="UNIFORM", amount_paise=50000))

    summary = report_service.dashboard(ReportFilter(year.id, as_of=date(2026, 10, 3)))
    assert summary["enrolled"] == 6 and summary["paid_up"] == 1
    assert summary["defaulters"] == 3 and summary["no_fees"] == 2
    assert summary["collected_paise"] == 1130000

    ukg_only = report_service.defaulters(ReportFilter(year.id, as_of=date(2026, 10, 3), student_class="UKG"))
    assert len(ukg_only) == 3
    vbn = ukg_only.set_index("Student").loc["VBN"]
    assert vbn["Overdue (Rs)"] == 1000 * 3 + 500  # Jul, Aug, Sep tuition + uniform
    assert vbn["Unpaid"].endswith("Uniform Fee")

    dg = report_service.dashboard(ReportFilter(year.id, as_of=date(2026, 10, 3), category="DG 1"))
    assert dg["enrolled"] == 1 and dg["defaulters"] == 1


def test_past_term_counts_every_unpaid_month(year):
    full_term = report_service.student_balances(ReportFilter(year.id, as_of=date(2027, 9, 1)))
    student = full_term.set_index("enrollment_id").loc[1]
    assert student["overdue_paise"] == student["balance_paise"] == 1870000


def test_trend_breakdowns_and_comparison(year):
    report_filter = ReportFilter(year.id, as_of=date(2026, 10, 3))
    trend = report_service.monthly_trend(report_filter)
    assert list(trend["Month"])[:2] == ["Jun 2026", "Jul 2026"] and len(trend) == 12
    assert trend.loc[0, "Collected in month"] == 3000 and trend.loc[1, "Collected in month"] == 8300
    assert trend.loc[4, "Paid against month"] == 1300
    classes = report_service.class_breakdown(report_filter)
    assert classes.iloc[0]["Class"] == "UKG-A"
    assert report_service.payment_method_split(report_filter).set_index("Method").loc["CASH", "Amount"] == 11300
    assert report_service.term_comparison().iloc[0]["Paid"] == 11300


def _sheet_names(sheets):
    workbook = load_workbook(BytesIO(build_workbook(sheets, "Test", "My School",
                                                    money_columns=report_service.MONEY_COLUMNS)))
    return workbook


def test_excel_reports_build(year):
    monthly = report_service.monthly_report(date(2026, 7, 1), include_all_students=True)
    assert set(monthly) >= {"Payments", "By fee type", "By method", "Students Jul 2026"}
    assert len(monthly["Payments"]) == 2 and monthly["Payments"]["Amount (Rs)"].sum() == 8300
    july = monthly["Students Jul 2026"].set_index("Student").loc["PRADEEP"]
    assert july["Month status"] == "Paid"

    workbook = _sheet_names(monthly)
    payments_sheet = workbook["Payments"]
    assert payments_sheet["A4"].value == "Receipt No" and payments_sheet["A1"].value == "Test - Payments"
    total_row = payments_sheet.max_row
    assert payments_sheet.cell(total_row, 1).value == "TOTAL"
    assert payments_sheet.cell(total_row, 8).value == "=SUM(H5:H6)"

    fy = report_service.financial_year_report(2026)
    assert fy["Monthly summary"]["Collected (Rs)"].sum() == 11300
    assert list(fy["By school term"]["Term"]) == ["2026-27"]

    operational = report_service.operational_year_report(ReportFilter(year.id, as_of=date(2026, 10, 3)))
    ledger = operational["Balances by month"].set_index("Student").loc["PRADEEP"]
    assert ledger["Oct 2026 (Rs)"] == 1200 and ledger["Balance (Rs)"] == 18700
    _sheet_names(operational)

    custom = report_service.custom_report(date(2026, 6, 1), date(2026, 7, 31), methods=["CASH"], fee_types=["TUITION"])
    assert custom["Fee details"]["Amount (Rs)"].sum() == 11300
    assert report_service.custom_report(date(2026, 6, 1), date(2026, 7, 31), methods=["UPI"])["Payments"].empty
    _sheet_names(custom)


def test_empty_workbook_is_valid():
    assert load_workbook(BytesIO(build_workbook({}, "Nothing"))).sheetnames == ["Empty"]
