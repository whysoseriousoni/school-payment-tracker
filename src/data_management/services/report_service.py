"""
Analytics and Excel report data.

Definitions (shared by the dashboard, defaulter list and reports):
  * Annual fees (tuition, van) are paid in instalments. On a given date the
    expected share is the highest payment-milestone % already reached (e.g. 50%
    by 31 Oct); at the end of the term the whole fee is expected.
  * One-off fees are expected from the day they were added.
  * "Paid" on a date counts only receipts dated on or before it.
  * Paid up = has fees and nothing overdue.  Defaulter = something overdue.
"""
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple

import pandas as pd

from data_management.dao import AcademicYear
from data_management.dto.fee import due_label, fee_type_label
from data_management.repositories import academic_year_repository
from data_management.repositories import report_repository as repo
from data_management.services.errors import NotFoundError
from data_management.sql_manager import session_scope
from helper import fee_rules
from helper.clock import today_ist
from helper.money import format_inr
from helper.school_calendar import (
    academic_year_label,
    academic_year_start_for,
    fee_months,
    financial_year_bounds,
    month_label,
)
from statics import ANNUAL_FEE_TYPES, CLASSES

STATUS_PAID = "Paid up"
STATUS_DEFAULTER = "Defaulter"
STATUS_NO_FEES = "No fees set"
_ANNUAL = {t.value for t in ANNUAL_FEE_TYPES}

Sheets = Dict[str, pd.DataFrame]


@dataclass(frozen=True)
class ReportFilter:
    academic_year_id: int
    as_of: Optional[date] = None
    student_class: Optional[str] = None
    section: Optional[str] = None
    category: Optional[str] = None


# ---------- helpers ----------

def _rupees(frame: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    frame = frame.copy()
    for column in columns:
        if column in frame:
            frame[column] = frame[column].fillna(0).astype("int64") / 100
    return frame


def _year(session, year_id: int) -> AcademicYear:
    year = academic_year_repository.get(session, year_id)
    if year is None:
        raise NotFoundError("Academic year not found")
    return year


def effective_as_of(year: AcademicYear, as_of: Optional[date] = None) -> date:
    as_of = as_of or today_ist()
    return max(year.start_date, min(as_of, year.end_date))


def _apply_filters(frame: pd.DataFrame, report_filter: ReportFilter) -> pd.DataFrame:
    for column in ("student_class", "section", "category"):
        value = getattr(report_filter, column)
        if value and column in frame:
            frame = frame[frame[column] == value]
    return frame


def _fee_type_label(value: str) -> str:
    return fee_type_label(value)


# ---------- core computation ----------

_BALANCE_COLUMNS = ["enrollment_id", "student_id", "admission_no", "name", "student_class", "section", "roll_no",
                    "category", "status", "guardian_name", "guardian_mobile", "fee_plan", "total_due_paise",
                    "total_paid_paise", "balance_paise", "expected_paise", "overdue_paise", "overdue_details",
                    "receipts", "payment_status"]


def _expected_for_dues(dues: pd.DataFrame, percent: int, as_of: date) -> pd.Series:
    return pd.Series([
        fee_rules.expected_amount(amount, percent) if fee_type in _ANNUAL
        else (amount if created <= as_of.isoformat() else 0)
        for fee_type, amount, created in zip(dues["fee_type"], dues["amount_due_paise"], dues["created_on"])
    ], index=dues.index, dtype="int64")


def _balances(session, report_filter: ReportFilter) -> Tuple[pd.DataFrame, AcademicYear, date]:
    year = _year(session, report_filter.academic_year_id)
    as_of = effective_as_of(year, report_filter.as_of)
    enrollments = _apply_filters(repo.enrollments(session, year.id), report_filter)
    if enrollments.empty:
        return pd.DataFrame(columns=_BALANCE_COLUMNS), year, as_of

    dues = repo.dues(session, year.id)
    dues = dues[dues["enrollment_id"].isin(enrollments["enrollment_id"])].copy()
    paid_by_due = repo.allocations(session, year_id=year.id, date_to=as_of).groupby("fee_due_id")["amount_paise"].sum()
    dues["paid"] = dues["fee_due_id"].map(paid_by_due).fillna(0).astype("int64")
    percent = fee_rules.expected_percent(repo.milestones(session, year.id), as_of, year.end_date)
    dues["expected"] = _expected_for_dues(dues, percent, as_of)
    dues["overdue"] = (dues["expected"] - dues["paid"]).clip(lower=0)
    dues["detail"] = [
        f"{due_label(t, d, c)}: {format_inr(o)}" if o > 0 else None
        for t, d, c, o in zip(dues["fee_type"], dues["description"], dues["plan_code"], dues["overdue"])
    ]
    tuition_plans = dues[dues["fee_type"] == "TUITION"].set_index("enrollment_id")["plan_code"]

    totals = dues.groupby("enrollment_id").agg(
        total_due_paise=("amount_due_paise", "sum"), total_paid_paise=("paid", "sum"),
        expected_paise=("expected", "sum"), overdue_paise=("overdue", "sum"),
        overdue_details=("detail", lambda items: "; ".join(i for i in items if isinstance(i, str) and i)),
    ).reset_index()
    payments = repo.payments(session, year_id=year.id, date_to=as_of)
    receipts = payments.groupby("enrollment_id")["payment_id"].count()

    frame = enrollments.merge(totals, on="enrollment_id", how="left")
    for column in ("total_due_paise", "total_paid_paise", "expected_paise", "overdue_paise"):
        frame[column] = frame[column].fillna(0).astype("int64")
    frame["balance_paise"] = frame["total_due_paise"] - frame["total_paid_paise"]
    frame["overdue_details"] = frame["overdue_details"].fillna("")
    frame["fee_plan"] = [
        (tuition_plans.get(eid) or "custom") if eid in tuition_plans.index else "not assigned"
        for eid in frame["enrollment_id"]
    ]
    frame["receipts"] = frame["enrollment_id"].map(receipts).fillna(0).astype("int64")
    frame["payment_status"] = [
        STATUS_NO_FEES if due == 0 else (STATUS_DEFAULTER if overdue > 0 else STATUS_PAID)
        for due, overdue in zip(frame["total_due_paise"], frame["overdue_paise"])
    ]
    frame["class_order"] = frame["student_class"].map(lambda c: CLASSES.index(c) if c in CLASSES else 99)
    frame = frame.sort_values(["class_order", "section", "roll_no", "name"], na_position="last")
    return frame[_BALANCE_COLUMNS].reset_index(drop=True), year, as_of


def student_balances(report_filter: ReportFilter) -> pd.DataFrame:
    with session_scope() as session:
        return _balances(session, report_filter)[0]


def dashboard(report_filter: ReportFilter) -> dict:
    with session_scope() as session:
        balances, year, as_of = _balances(session, report_filter)
        payments = repo.payments(session, year_id=year.id)
        payments = payments[payments["enrollment_id"].isin(balances["enrollment_id"])]
        milestones = repo.milestones(session, year.id)
    today = today_ist()
    return {
        "year_label": year.label,
        "as_of": as_of,
        "expected_percent": fee_rules.expected_percent(milestones, as_of, year.end_date),
        "next_milestone": fee_rules.next_milestone(milestones, as_of),
        "has_milestones": bool(milestones),
        "enrolled": int(len(balances)),
        "paid_up": int((balances["payment_status"] == STATUS_PAID).sum()),
        "defaulters": int((balances["payment_status"] == STATUS_DEFAULTER).sum()),
        "no_fees": int((balances["payment_status"] == STATUS_NO_FEES).sum()),
        "expected_paise": int(balances["total_due_paise"].sum()),
        "expected_by_now_paise": int(balances["expected_paise"].sum()),
        "collected_paise": int(balances["total_paid_paise"].sum()),
        "overdue_paise": int(balances["overdue_paise"].sum()),
        "remaining_paise": int(balances["balance_paise"].sum()),
        "collected_today_paise": int(payments.loc[payments["paid_on"] == today.isoformat(), "amount_paise"].sum()),
        "collected_this_month_paise": int(
            payments.loc[payments["paid_on"].str[:7] == today.isoformat()[:7], "amount_paise"].sum()),
    }


def monthly_trend(report_filter: ReportFilter) -> pd.DataFrame:
    """Per month of the term: money collected, cumulative collected, and what milestones expected by month end."""
    with session_scope() as session:
        balances, year, _ = _balances(session, report_filter)
        dues = repo.dues(session, year.id)
        dues = dues[dues["enrollment_id"].isin(balances["enrollment_id"])]
        payments = repo.payments(session, year_id=year.id)
        payments = payments[payments["enrollment_id"].isin(balances["enrollment_id"])]
        milestones = repo.milestones(session, year.id)
    collected = payments.groupby(payments["paid_on"].str[:7])["amount_paise"].sum()
    rows, running = [], 0
    for month in fee_months(year.start_date.year):
        month_end = (pd.Timestamp(month) + pd.offsets.MonthEnd(0)).date()
        in_month = int(collected.get(month.isoformat()[:7], 0))
        running += in_month
        percent = fee_rules.expected_percent(milestones, month_end, year.end_date)
        expected = int(_expected_for_dues(dues, percent, month_end).sum()) if len(dues) else 0
        rows.append({"Month": month_label(month), "Collected in month": in_month / 100,
                     "Collected so far": running / 100, "Expected by month end": expected / 100})
    return pd.DataFrame(rows)


def class_breakdown(report_filter: ReportFilter) -> pd.DataFrame:
    balances = student_balances(report_filter)
    if balances.empty:
        return pd.DataFrame()
    balances["Defaulter"] = (balances["payment_status"] == STATUS_DEFAULTER).astype(int)
    grouped = balances.groupby(["student_class", "section"]).agg(
        Students=("enrollment_id", "count"), Defaulters=("Defaulter", "sum"),
        Due=("total_due_paise", "sum"), Paid=("total_paid_paise", "sum"), Overdue=("overdue_paise", "sum"),
    ).reset_index()
    grouped = _rupees(grouped, ["Due", "Paid", "Overdue"])
    grouped["order"] = grouped["student_class"].map(lambda c: CLASSES.index(c) if c in CLASSES else 99)
    grouped = grouped.sort_values(["order", "section"]).drop(columns="order")
    grouped.insert(0, "Class", grouped.pop("student_class") + "-" + grouped.pop("section"))
    return grouped.reset_index(drop=True)


def category_breakdown(report_filter: ReportFilter) -> pd.DataFrame:
    balances = student_balances(report_filter)
    if balances.empty:
        return pd.DataFrame()
    balances["category"] = balances["category"].fillna("Not set")
    balances["Defaulter"] = (balances["payment_status"] == STATUS_DEFAULTER).astype(int)
    grouped = balances.groupby("category").agg(
        Students=("enrollment_id", "count"), Defaulters=("Defaulter", "sum"),
        Due=("total_due_paise", "sum"), Paid=("total_paid_paise", "sum"), Overdue=("overdue_paise", "sum")
    ).reset_index()
    return _rupees(grouped.rename(columns={"category": "Category"}), ["Due", "Paid", "Overdue"])


def payment_method_split(report_filter: ReportFilter) -> pd.DataFrame:
    with session_scope() as session:
        balances, year, _ = _balances(session, report_filter)
        payments = repo.payments(session, year_id=year.id)
    payments = payments[payments["enrollment_id"].isin(balances["enrollment_id"])]
    if payments.empty:
        return pd.DataFrame(columns=["Method", "Receipts", "Amount"])
    grouped = payments.groupby("payment_method").agg(Receipts=("payment_id", "count"),
                                                      Amount=("amount_paise", "sum")).reset_index()
    return _rupees(grouped.rename(columns={"payment_method": "Method"}), ["Amount"])


def term_comparison() -> pd.DataFrame:
    rows = []
    with session_scope() as session:
        for year in repo.years(session).itertuples():
            dues = repo.dues(session, year.id)
            rows.append({"Term": year.label, "Due": dues["amount_due_paise"].sum() / 100,
                         "Paid": dues["amount_paid_paise"].sum() / 100,
                         "Outstanding": dues["balance_paise"].sum() / 100})
    return pd.DataFrame(rows)


def _student_sheet(balances: pd.DataFrame) -> pd.DataFrame:
    frame = _rupees(balances, ["total_due_paise", "total_paid_paise", "balance_paise", "expected_paise",
                               "overdue_paise"])
    return frame.rename(columns={
        "admission_no": "Admission No", "name": "Student", "student_class": "Class", "section": "Section",
        "roll_no": "Roll No", "category": "Category", "fee_plan": "Tuition plan", "total_due_paise": "Due (Rs)",
        "total_paid_paise": "Paid (Rs)", "balance_paise": "Balance (Rs)", "expected_paise": "Expected by now (Rs)",
        "overdue_paise": "Overdue (Rs)", "overdue_details": "Overdue fees", "receipts": "Receipts",
        "payment_status": "Status", "guardian_name": "Guardian", "guardian_mobile": "Mobile",
    })[["Admission No", "Student", "Class", "Section", "Roll No", "Category", "Tuition plan", "Due (Rs)",
        "Paid (Rs)", "Balance (Rs)", "Expected by now (Rs)", "Overdue (Rs)", "Overdue fees", "Receipts",
        "Status", "Guardian", "Mobile"]].reset_index(drop=True)


def defaulters(report_filter: ReportFilter) -> pd.DataFrame:
    balances = student_balances(report_filter)
    sheet = _student_sheet(balances[balances["payment_status"] == STATUS_DEFAULTER])
    return sheet.drop(columns=["Status"])


# ---------- Excel report sheets ----------

MONEY_COLUMNS = {"Amount (Rs)", "Due (Rs)", "Paid (Rs)", "Balance (Rs)", "Overdue (Rs)", "Expected by now (Rs)",
                 "Paid in month (Rs)", "Collected (Rs)", "Due", "Paid", "Overdue", "Outstanding", "Amount",
                 "Collected in month", "Collected so far", "Expected by month end"}


def _payments_sheet(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["Receipt No", "Paid On", "Student", "Admission No", "Class", "Term",
                                     "Method", "Amount (Rs)", "Reference", "Billing Name", "Collected By"])
    frame = _rupees(frame, ["amount_paise"])
    frame["Class"] = frame["student_class"] + "-" + frame["section"]
    return frame.rename(columns={
        "receipt_no": "Receipt No", "paid_on": "Paid On", "name": "Student", "admission_no": "Admission No",
        "academic_year": "Term", "payment_method": "Method", "amount_paise": "Amount (Rs)",
        "payment_notes": "Reference", "billing_name": "Billing Name", "collected_by": "Collected By",
    })[["Receipt No", "Paid On", "Student", "Admission No", "Class", "Term", "Method", "Amount (Rs)",
        "Reference", "Billing Name", "Collected By"]]


def _fee_type_sheet(allocations: pd.DataFrame) -> pd.DataFrame:
    if allocations.empty:
        return pd.DataFrame(columns=["Fee", "Amount (Rs)"])
    grouped = allocations.groupby("fee_type")["amount_paise"].sum().reset_index()
    grouped["Fee"] = grouped["fee_type"].map(_fee_type_label)
    return _rupees(grouped, ["amount_paise"]).rename(columns={"amount_paise": "Amount (Rs)"})[["Fee", "Amount (Rs)"]]


def _method_sheet(payments: pd.DataFrame) -> pd.DataFrame:
    if payments.empty:
        return pd.DataFrame(columns=["Method", "Receipts", "Amount (Rs)"])
    grouped = payments.groupby("payment_method").agg(Receipts=("payment_id", "count"),
                                                      amount=("amount_paise", "sum")).reset_index()
    return _rupees(grouped, ["amount"]).rename(columns={"payment_method": "Method", "amount": "Amount (Rs)"})


def _filter_payments(payments: pd.DataFrame, report_filter: Optional[ReportFilter],
                     methods: Optional[List[str]] = None) -> pd.DataFrame:
    if report_filter:
        payments = _apply_filters(payments, report_filter)
    if methods:
        payments = payments[payments["payment_method"].isin(methods)]
    return payments


def monthly_report(month: date, include_all_students: bool, report_filter: Optional[ReportFilter] = None) -> Sheets:
    """Collections in a calendar month; optionally every student's position at the end of that month."""
    month = month.replace(day=1)
    month_end = (pd.Timestamp(month) + pd.offsets.MonthEnd(0)).date()
    with session_scope() as session:
        payments = _filter_payments(repo.payments(session, date_from=month, date_to=month_end), report_filter)
        allocations = repo.allocations(session, date_from=month, date_to=month_end)
        allocations = allocations[allocations["payment_id"].isin(payments["payment_id"])]
        voided = _filter_payments(repo.payments(session, date_from=month, date_to=month_end, include_voided=True),
                                  report_filter)
        voided = voided[voided["is_voided"] == 1]
        sheets: Sheets = {
            "Payments": _payments_sheet(payments),
            "By fee type": _fee_type_sheet(allocations),
            "By method": _method_sheet(payments),
        }
        if len(voided):
            voided_sheet = _payments_sheet(voided)
            voided_sheet["Void reason"] = voided["void_reason"].values
            sheets["Voided receipts"] = voided_sheet

        if include_all_students:
            year = academic_year_repository.get_by_label(session, academic_year_label(academic_year_start_for(month)))
            if year is not None:
                base = report_filter or ReportFilter(academic_year_id=year.id)
                year_filter = ReportFilter(academic_year_id=year.id, as_of=month_end, student_class=base.student_class,
                                           section=base.section, category=base.category)
                balances, _, _ = _balances(session, year_filter)
                sheet = _student_sheet(balances)
                paid_in_month = payments.groupby("enrollment_id")["amount_paise"].sum()
                sheet.insert(8, "Paid in month (Rs)",
                             balances["enrollment_id"].map(paid_in_month).fillna(0).values / 100)
                sheets[f"Students at {month_end:%d %b %Y}"] = sheet
    return sheets


def financial_year_report(start_year: int, report_filter: Optional[ReportFilter] = None) -> Sheets:
    """April -> March, grouped by payment date (spans two school years)."""
    date_from, date_to = financial_year_bounds(start_year)
    with session_scope() as session:
        payments = _filter_payments(repo.payments(session, date_from=date_from, date_to=date_to), report_filter)
        allocations = repo.allocations(session, date_from=date_from, date_to=date_to)
        allocations = allocations[allocations["payment_id"].isin(payments["payment_id"])]
    monthly = pd.DataFrame(columns=["Month", "Receipts", "Collected (Rs)"])
    by_term = pd.DataFrame(columns=["Term", "Amount (Rs)"])
    if len(payments):
        grouped = payments.groupby(payments["paid_on"].str[:7]).agg(
            Receipts=("payment_id", "count"), collected=("amount_paise", "sum")).reset_index()
        grouped["Month"] = grouped["paid_on"].map(lambda value: month_label(date.fromisoformat(value + "-01")))
        monthly = _rupees(grouped, ["collected"]).rename(columns={"collected": "Collected (Rs)"})[
            ["Month", "Receipts", "Collected (Rs)"]]
        by_term = _rupees(payments.groupby("academic_year")["amount_paise"].sum().reset_index(), ["amount_paise"]) \
            .rename(columns={"academic_year": "Term", "amount_paise": "Amount (Rs)"})
    return {"Monthly summary": monthly, "By fee type": _fee_type_sheet(allocations),
            "By method": _method_sheet(payments), "By school term": by_term, "Payments": _payments_sheet(payments)}


def operational_year_report(report_filter: ReportFilter) -> Sheets:
    """Full school term (June -> May): summary, student balances, payments per month, class summary, receipts."""
    summary = dashboard(report_filter)
    with session_scope() as session:
        balances, year, _ = _balances(session, report_filter)
        payments = repo.payments(session, year_id=year.id)
        payments = payments[payments["enrollment_id"].isin(balances["enrollment_id"])]

    next_milestone = summary["next_milestone"]
    summary_sheet = pd.DataFrame([
        ("Term", summary["year_label"]), ("As of", summary["as_of"].isoformat()),
        ("Expected share of annual fees by now", f"{summary['expected_percent']}%"),
        ("Next milestone", f"{next_milestone[1]}% by {next_milestone[0]:%d %b %Y}" if next_milestone else "-"),
        ("Students enrolled", summary["enrolled"]), ("Paid up", summary["paid_up"]),
        ("Defaulters", summary["defaulters"]), ("No fees set", summary["no_fees"]),
        ("Fees for term (Rs)", summary["expected_paise"] / 100),
        ("Expected by now (Rs)", summary["expected_by_now_paise"] / 100),
        ("Collected (Rs)", summary["collected_paise"] / 100),
        ("Overdue (Rs)", summary["overdue_paise"] / 100),
        ("Remaining for term (Rs)", summary["remaining_paise"] / 100),
    ], columns=["Measure", "Value"])

    grid = balances[["enrollment_id", "admission_no", "name", "student_class", "section", "roll_no"]].copy()
    paid_by_month = payments.groupby(["enrollment_id", payments["paid_on"].str[:7]])["amount_paise"].sum()
    for month in fee_months(year.start_date.year):
        key = month.isoformat()[:7]
        grid[f"{month_label(month)} (Rs)"] = [paid_by_month.get((eid, key), 0) / 100 for eid in grid["enrollment_id"]]
    grid["Paid (Rs)"] = balances["total_paid_paise"].values / 100
    grid["Balance (Rs)"] = balances["balance_paise"].values / 100
    grid = grid.drop(columns="enrollment_id").rename(columns={
        "admission_no": "Admission No", "name": "Student", "student_class": "Class", "section": "Section",
        "roll_no": "Roll No"})
    return {"Summary": summary_sheet, "Student balances": _student_sheet(balances),
            "Paid per month": grid, "Class summary": class_breakdown(report_filter),
            "Payments": _payments_sheet(payments)}


def custom_report(date_from: date, date_to: date, report_filter: Optional[ReportFilter] = None,
                  methods: Optional[List[str]] = None, fee_types: Optional[List[str]] = None) -> Sheets:
    with session_scope() as session:
        payments = _filter_payments(repo.payments(session, date_from=date_from, date_to=date_to), report_filter,
                                    methods)
        allocations = repo.allocations(session, date_from=date_from, date_to=date_to)
    allocations = allocations[allocations["payment_id"].isin(payments["payment_id"])]
    if fee_types:
        allocations = allocations[allocations["fee_type"].isin(fee_types)]
        payments = payments[payments["payment_id"].isin(allocations["payment_id"])]
    detail = pd.DataFrame(columns=["Receipt No", "Paid On", "Fee", "Amount (Rs)"])
    if len(allocations):
        detail = allocations.copy()
        detail["Fee"] = [due_label(t, d, c) for t, d, c in
                         zip(detail["fee_type"], detail["description"], detail["plan_code"])]
        detail = _rupees(detail, ["amount_paise"]).rename(columns={
            "receipt_no": "Receipt No", "paid_on": "Paid On", "amount_paise": "Amount (Rs)"})[
            ["Receipt No", "Paid On", "Fee", "Amount (Rs)"]]
    return {"Payments": _payments_sheet(payments), "Fee details": detail,
            "By fee type": _fee_type_sheet(allocations), "By method": _method_sheet(payments)}
