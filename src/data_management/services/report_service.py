"""
Analytics and Excel report data.

Definitions (shared by the dashboard, defaulter list and reports):
  * A monthly fee is overdue from FEE_DUE_DAY of its month; a one-off fee is
    overdue from the day it was added.
  * For the current term "as of" is today; for a finished term it is the term's
    last day, so every unpaid due counts.
  * Paid up  = enrolled, has fees, nothing overdue.  Defaulter = something overdue.
"""
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple

import pandas as pd

from config.settings import FEE_DUE_DAY
from data_management.dao import AcademicYear
from data_management.dto.fee import due_label
from data_management.repositories import academic_year_repository
from data_management.repositories import report_repository as repo
from data_management.services.errors import NotFoundError
from data_management.sql_manager import session_scope
from helper.clock import today_ist
from helper.school_calendar import (
    academic_year_label,
    academic_year_start_for,
    fee_months,
    financial_year_bounds,
    last_overdue_month,
    month_label,
)
from statics import FEE_TYPE_LABELS, FeeType

STATUS_PAID = "Paid up"
STATUS_DEFAULTER = "Defaulter"
STATUS_NO_FEES = "No fees set"

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
    try:
        return FEE_TYPE_LABELS[FeeType(value)]
    except ValueError:
        return value


def _parse_month(series: pd.Series) -> pd.Series:
    return series.map(lambda value: date.fromisoformat(value) if isinstance(value, str) and value else None)


# ---------- core computation ----------

_BALANCE_COLUMNS = ["enrollment_id", "student_id", "admission_no", "name", "student_class", "section", "roll_no",
                    "category", "status", "guardian_name", "guardian_mobile", "total_due_paise", "total_paid_paise",
                    "balance_paise", "overdue_paise", "overdue_months", "payment_status"]


def _balances(session, report_filter: ReportFilter) -> Tuple[pd.DataFrame, AcademicYear, date]:
    year = _year(session, report_filter.academic_year_id)
    as_of = effective_as_of(year, report_filter.as_of)
    enrollments = _apply_filters(repo.enrollments(session, year.id), report_filter)
    if enrollments.empty:
        return pd.DataFrame(columns=_BALANCE_COLUMNS), year, as_of

    dues = repo.dues(session, year.id)
    dues = dues[dues["enrollment_id"].isin(enrollments["enrollment_id"])].copy()
    cutoff = last_overdue_month(as_of, FEE_DUE_DAY)
    dues["month"] = _parse_month(dues["fee_month"])
    recurring_overdue = dues["month"].map(lambda m: m is not None and m <= cutoff)
    one_off_overdue = dues["month"].isna() & (dues["created_on"] <= as_of.isoformat())
    dues["is_overdue"] = recurring_overdue | one_off_overdue
    dues["overdue_balance"] = dues["balance_paise"].where(dues["is_overdue"], 0)
    dues["overdue_label"] = [
        due_label(t, m, d) if overdue and balance > 0 else None
        for t, m, d, overdue, balance in zip(dues["fee_type"], dues["month"], dues["description"],
                                              dues["is_overdue"], dues["balance_paise"])
    ]

    totals = dues.groupby("enrollment_id").agg(
        total_due_paise=("amount_due_paise", "sum"), total_paid_paise=("amount_paid_paise", "sum"),
        balance_paise=("balance_paise", "sum"), overdue_paise=("overdue_balance", "sum"),
        overdue_months=("overdue_label", lambda labels: ", ".join(l for l in labels if isinstance(l, str) and l)),
    ).reset_index()
    frame = enrollments.merge(totals, on="enrollment_id", how="left")
    for column in ("total_due_paise", "total_paid_paise", "balance_paise", "overdue_paise"):
        frame[column] = frame[column].fillna(0).astype("int64")
    frame["overdue_months"] = frame["overdue_months"].fillna("")
    frame["payment_status"] = [
        STATUS_NO_FEES if due == 0 else (STATUS_DEFAULTER if overdue > 0 else STATUS_PAID)
        for due, overdue in zip(frame["total_due_paise"], frame["overdue_paise"])
    ]
    frame = frame.sort_values(["student_class", "section", "roll_no", "name"], na_position="last")
    return frame[_BALANCE_COLUMNS].reset_index(drop=True), year, as_of


def student_balances(report_filter: ReportFilter) -> pd.DataFrame:
    with session_scope() as session:
        return _balances(session, report_filter)[0]


def dashboard(report_filter: ReportFilter) -> dict:
    with session_scope() as session:
        balances, year, as_of = _balances(session, report_filter)
        payments = repo.payments(session, year_id=year.id)
        payments = payments[payments["enrollment_id"].isin(balances["enrollment_id"])]
        today = today_ist()
        return {
            "year_label": year.label,
            "as_of": as_of,
            "enrolled": int(len(balances)),
            "paid_up": int((balances["payment_status"] == STATUS_PAID).sum()),
            "defaulters": int((balances["payment_status"] == STATUS_DEFAULTER).sum()),
            "no_fees": int((balances["payment_status"] == STATUS_NO_FEES).sum()),
            "expected_paise": int(balances["total_due_paise"].sum()),
            "collected_paise": int(payments["amount_paise"].sum()),
            "overdue_paise": int(balances["overdue_paise"].sum()),
            "remaining_paise": int(balances["balance_paise"].sum()),
            "collected_today_paise": int(payments.loc[payments["paid_on"] == today.isoformat(), "amount_paise"].sum()),
            "collected_this_month_paise": int(
                payments.loc[payments["paid_on"].str[:7] == today.isoformat()[:7], "amount_paise"].sum()),
        }


def monthly_trend(report_filter: ReportFilter) -> pd.DataFrame:
    """Per fee month (Jun -> May): dues raised, paid against them, and money collected in that month."""
    with session_scope() as session:
        balances, year, _ = _balances(session, report_filter)
        months = fee_months(year.start_date.year)
        dues = repo.dues(session, year.id)
        dues = dues[dues["enrollment_id"].isin(balances["enrollment_id"]) & dues["fee_month"].notna()]
        by_month = dues.groupby("fee_month")[["amount_due_paise", "amount_paid_paise"]].sum()
        payments = repo.payments(session, year_id=year.id)
        payments = payments[payments["enrollment_id"].isin(balances["enrollment_id"])]
        collected = payments.groupby(payments["paid_on"].str[:7])["amount_paise"].sum()
    rows = []
    for month in months:
        key = month.isoformat()
        rows.append({
            "Month": month_label(month),
            "Due": by_month["amount_due_paise"].get(key, 0) / 100,
            "Paid against month": by_month["amount_paid_paise"].get(key, 0) / 100,
            "Collected in month": collected.get(key[:7], 0) / 100,
        })
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
    from statics import CLASSES

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
        Paid=("total_paid_paise", "sum"), Overdue=("overdue_paise", "sum")).reset_index()
    return _rupees(grouped.rename(columns={"category": "Category"}), ["Paid", "Overdue"])


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


def defaulters(report_filter: ReportFilter) -> pd.DataFrame:
    balances = student_balances(report_filter)
    frame = balances[balances["payment_status"] == STATUS_DEFAULTER]
    frame = _rupees(frame, ["overdue_paise", "balance_paise"])
    return frame.rename(columns={
        "admission_no": "Admission No", "name": "Student", "student_class": "Class", "section": "Section",
        "roll_no": "Roll No", "category": "Category", "overdue_months": "Unpaid", "overdue_paise": "Overdue (Rs)",
        "balance_paise": "Balance for year (Rs)", "guardian_name": "Guardian", "guardian_mobile": "Mobile",
    })[["Admission No", "Student", "Class", "Section", "Roll No", "Category", "Unpaid", "Overdue (Rs)",
        "Balance for year (Rs)", "Guardian", "Mobile"]].reset_index(drop=True)


# ---------- Excel report sheets ----------

MONEY_COLUMNS = {"Amount (Rs)", "Due (Rs)", "Paid (Rs)", "Balance (Rs)", "Overdue (Rs)", "Balance for year (Rs)",
                 "Tuition due (Rs)", "Tuition paid (Rs)", "Van due (Rs)", "Van paid (Rs)", "Due", "Paid",
                 "Overdue", "Outstanding", "Amount", "Collected in month", "Due in month", "Paid against month",
                 "Collected (Rs)"}


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
    """Collections in a calendar month; optionally every student's status for that fee month."""
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
                dues = repo.dues(session, year.id)
                dues = dues[dues["fee_month"] == month.isoformat()]
                pivot = dues.pivot_table(index="enrollment_id", columns="fee_type",
                                         values=["amount_due_paise", "amount_paid_paise"], aggfunc="sum", fill_value=0)
                status = balances[["enrollment_id", "admission_no", "name", "student_class", "section", "roll_no",
                                   "guardian_mobile", "overdue_paise"]].copy()
                for fee_type, label in (("TUITION", "Tuition"), ("VAN", "Van")):
                    for measure, suffix in (("amount_due_paise", "due"), ("amount_paid_paise", "paid")):
                        column = (measure, fee_type)
                        values = pivot[column] if column in pivot.columns else pd.Series(dtype="int64")
                        status[f"{label} {suffix} (Rs)"] = status["enrollment_id"].map(values).fillna(0) / 100
                status["Overdue (Rs)"] = status.pop("overdue_paise") / 100
                status["Month status"] = [
                    "No fee" if due == 0 else ("Paid" if paid >= due else ("Part paid" if paid else "Unpaid"))
                    for due, paid in zip(status["Tuition due (Rs)"] + status["Van due (Rs)"],
                                         status["Tuition paid (Rs)"] + status["Van paid (Rs)"])
                ]
                sheets[f"Students {month_label(month)}"] = status.drop(columns="enrollment_id").rename(columns={
                    "admission_no": "Admission No", "name": "Student", "student_class": "Class",
                    "section": "Section", "roll_no": "Roll No", "guardian_mobile": "Mobile"})
    return sheets


def financial_year_report(start_year: int, report_filter: Optional[ReportFilter] = None) -> Sheets:
    """April -> March, grouped by payment date (spans two school years)."""
    date_from, date_to = financial_year_bounds(start_year)
    with session_scope() as session:
        payments = _filter_payments(repo.payments(session, date_from=date_from, date_to=date_to), report_filter)
        allocations = repo.allocations(session, date_from=date_from, date_to=date_to)
        allocations = allocations[allocations["payment_id"].isin(payments["payment_id"])]
    monthly = pd.DataFrame(columns=["Month", "Receipts", "Collected (Rs)"])
    if len(payments):
        grouped = payments.groupby(payments["paid_on"].str[:7]).agg(
            Receipts=("payment_id", "count"), collected=("amount_paise", "sum")).reset_index()
        grouped["Month"] = grouped["paid_on"].map(lambda value: month_label(date.fromisoformat(value + "-01")))
        monthly = _rupees(grouped, ["collected"]).rename(columns={"collected": "Collected (Rs)"})[
            ["Month", "Receipts", "Collected (Rs)"]]
    by_term = pd.DataFrame(columns=["Term", "Amount (Rs)"])
    if len(payments):
        by_term = _rupees(payments.groupby("academic_year")["amount_paise"].sum().reset_index(), ["amount_paise"]) \
            .rename(columns={"academic_year": "Term", "amount_paise": "Amount (Rs)"})
    return {"Monthly summary": monthly, "By fee type": _fee_type_sheet(allocations),
            "By method": _method_sheet(payments), "By school term": by_term, "Payments": _payments_sheet(payments)}


def operational_year_report(report_filter: ReportFilter) -> Sheets:
    """Full school term (June -> May): summary, student x month ledger, payments, class summary."""
    summary = dashboard(report_filter)
    with session_scope() as session:
        balances, year, _ = _balances(session, report_filter)
        dues = repo.dues(session, year.id)
        dues = dues[dues["enrollment_id"].isin(balances["enrollment_id"])]
        payments = repo.payments(session, year_id=year.id)
        payments = payments[payments["enrollment_id"].isin(balances["enrollment_id"])]

    summary_sheet = pd.DataFrame([
        ("Term", summary["year_label"]), ("As of", summary["as_of"].isoformat()),
        ("Students enrolled", summary["enrolled"]), ("Paid up", summary["paid_up"]),
        ("Defaulters", summary["defaulters"]), ("No fees set", summary["no_fees"]),
        ("Expected for term (Rs)", summary["expected_paise"] / 100),
        ("Collected (Rs)", summary["collected_paise"] / 100),
        ("Overdue (Rs)", summary["overdue_paise"] / 100),
        ("Remaining for term (Rs)", summary["remaining_paise"] / 100),
    ], columns=["Measure", "Value"])

    ledger = balances[["enrollment_id", "admission_no", "name", "student_class", "section", "roll_no"]].copy()
    recurring = dues[dues["fee_month"].notna()]
    month_balance = recurring.groupby(["enrollment_id", "fee_month"])["balance_paise"].sum()
    month_columns = []
    for month in fee_months(year.start_date.year):
        column = f"{month_label(month)} (Rs)"
        month_columns.append(column)
        ledger[column] = [month_balance.get((eid, month.isoformat()), 0) / 100 for eid in ledger["enrollment_id"]]
    one_off = dues[dues["fee_month"].isna()].groupby("enrollment_id")["balance_paise"].sum()
    ledger["Other fees (Rs)"] = ledger["enrollment_id"].map(one_off).fillna(0) / 100
    ledger["Paid (Rs)"] = balances["total_paid_paise"].values / 100
    ledger["Balance (Rs)"] = balances["balance_paise"].values / 100
    ledger["Overdue (Rs)"] = balances["overdue_paise"].values / 100
    ledger = ledger.drop(columns="enrollment_id").rename(columns={
        "admission_no": "Admission No", "name": "Student", "student_class": "Class", "section": "Section",
        "roll_no": "Roll No"})

    return {"Summary": summary_sheet, "Balances by month": ledger, "Class summary": class_breakdown(report_filter),
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
        detail["Fee"] = [due_label(t, date.fromisoformat(m) if isinstance(m, str) else None, d)
                         for t, m, d in zip(detail["fee_type"], detail["fee_month"], detail["description"])]
        detail = _rupees(detail, ["amount_paise"]).rename(columns={
            "receipt_no": "Receipt No", "paid_on": "Paid On", "amount_paise": "Amount (Rs)"})[
            ["Receipt No", "Paid On", "Fee", "Amount (Rs)"]]
    return {"Payments": _payments_sheet(payments), "Fee details": detail,
            "By fee type": _fee_type_sheet(allocations), "By method": _method_sheet(payments)}
