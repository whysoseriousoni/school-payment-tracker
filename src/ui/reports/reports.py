from datetime import date

import streamlit as st

from data_management.services import academic_year_service, report_service, settings_service
from data_management.services.report_service import ReportFilter
from helper.clock import today_ist
from helper.school_calendar import academic_year_start_for
from reports.excel import build_workbook
from statics import CLASSES, FEE_TYPE_LABELS, PAYMENT_METHODS, SECTIONS, STUDENT_CATEGORY, FeeType
from ui.common import optional_select, page_header, require_user, run_action, term_select

user = require_user()
page_header("Excel reports")

REPORTS = {
    "Monthly": "Receipts in one calendar month - paid only, or with every student's status for that month.",
    "Financial year (April - March)": "All collections in a financial year, by payment date.",
    "School term (June - May)": "Full term: summary, each student's month-by-month balance, payments.",
    "Custom": "Any date range, with mode and fee filters.",
}
kind = st.radio("Report", list(REPORTS), horizontal=True)
st.caption(REPORTS[kind])

years = academic_year_service.list_years()
f1, f2, f3 = st.columns(3)
with f1:
    student_class = optional_select("Class", CLASSES, key="rep_class")
with f2:
    section = optional_select("Section", SECTIONS, key="rep_section")
with f3:
    category = optional_select("Category", STUDENT_CATEGORY, key="rep_category")


def filter_for(year_id: int) -> ReportFilter:
    return ReportFilter(academic_year_id=year_id, student_class=student_class, section=section, category=category)


current_id = next((y.id for y in years if y.is_current), years[0].id if years else 0)
sheets, title, file_stub = None, "", ""

if kind == "Monthly":
    m1, m2, m3 = st.columns(3)
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    month_no = m1.selectbox("Month", range(1, 13), index=today_ist().month - 1, format_func=lambda m: month_names[m - 1])
    year_no = m2.number_input("Year", min_value=2000, max_value=2100, value=today_ist().year)
    mode = m3.radio("Include", ["Paid only", "All students"], horizontal=True)
    if st.button("Generate", type="primary"):
        month = date(int(year_no), month_no, 1)
        sheets = run_action(report_service.monthly_report, month, mode == "All students", filter_for(current_id))
        title, file_stub = f"Monthly report {month:%b %Y}", f"monthly_{month:%Y_%m}"

elif kind.startswith("Financial"):
    today = today_ist()
    default_start = today.year if today.month >= 4 else today.year - 1
    fy_start = st.selectbox("Financial year", list(range(default_start, default_start - 8, -1)),
                            format_func=lambda y: f"FY {y}-{(y + 1) % 100:02d} (Apr {y} - Mar {y + 1})")
    if st.button("Generate", type="primary"):
        sheets = run_action(report_service.financial_year_report, fy_start, filter_for(current_id))
        title, file_stub = f"Financial year {fy_start}-{(fy_start + 1) % 100:02d}", f"financial_year_{fy_start}"

elif kind.startswith("School term"):
    term = term_select(key="rep_term", years=years)
    if term and st.button("Generate", type="primary"):
        sheets = run_action(report_service.operational_year_report, filter_for(term.id))
        title, file_stub = f"School term {term.label}", f"school_term_{term.label}"

else:
    c1, c2 = st.columns(2)
    date_from = c1.date_input("From", value=today_ist().replace(day=1), format="DD/MM/YYYY")
    date_to = c2.date_input("To", value=today_ist(), format="DD/MM/YYYY")
    c3, c4 = st.columns(2)
    methods = c3.multiselect("Payment modes", PAYMENT_METHODS, placeholder="All modes")
    fee_types = c4.multiselect("Fee types", [t.value for t in FeeType], placeholder="All fees",
                               format_func=lambda t: FEE_TYPE_LABELS[FeeType(t)])
    if st.button("Generate", type="primary"):
        if date_from > date_to:
            st.error("'From' must be before 'To'.")
        else:
            year_id = next((y.id for y in years if y.start_date.year == academic_year_start_for(date_from)), current_id)
            sheets = run_action(report_service.custom_report, date_from, date_to, filter_for(year_id),
                                methods or None, fee_types or None)
            title, file_stub = f"Collections {date_from:%d %b %Y} - {date_to:%d %b %Y}", \
                f"custom_{date_from:%Y%m%d}_{date_to:%Y%m%d}"

if sheets is not None:
    school = settings_service.get_settings()[settings_service.SCHOOL_NAME]
    content = build_workbook(sheets, title, school, money_columns=report_service.MONEY_COLUMNS)
    st.download_button(f"Download {title}.xlsx", content, file_name=f"{file_stub}.xlsx", type="primary",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    for name, frame in sheets.items():
        with st.expander(f"{name} ({len(frame)} rows)", expanded=name == next(iter(sheets))):
            st.dataframe(frame, hide_index=True, width="stretch")
