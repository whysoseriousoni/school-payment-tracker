from datetime import timedelta

import streamlit as st

from config.settings import FEE_DUE_DAY
from data_management.services import academic_year_service, report_service, settings_service
from data_management.services.report_service import ReportFilter
from helper.clock import today_ist
from reports.excel import build_workbook
from statics import CLASSES, SECTIONS, STUDENT_CATEGORY
from ui.common import optional_select, page_header, require_user, rupees, term_select

user = require_user()
page_header("Summary", f"Monthly fees become overdue on the {FEE_DUE_DAY}th of each month.")

years = academic_year_service.list_years()
f1, f2, f3, f4, f5 = st.columns([2, 1, 1, 1.5, 2])
with f1:
    term = term_select(key="sum_term", years=years)
with f2:
    student_class = optional_select("Class", CLASSES, key="sum_class")
with f3:
    section = optional_select("Section", SECTIONS, key="sum_section")
with f4:
    category = optional_select("Category", STUDENT_CATEGORY, key="sum_category")
if term is None:
    st.stop()
default_as_of = max(term.start_date, min(today_ist(), term.end_date))
as_of = f5.date_input("Status as of", value=default_as_of, min_value=term.start_date, max_value=term.end_date,
                      format="DD/MM/YYYY", key=f"sum_as_of_{term.id}")

report_filter = ReportFilter(academic_year_id=term.id, as_of=as_of, student_class=student_class, section=section,
                             category=category)
summary = report_service.dashboard(report_filter)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Students enrolled", summary["enrolled"])
k2.metric("Paid up", summary["paid_up"])
k3.metric("Have overdue fees", summary["defaulters"])
k4.metric("No fees set", summary["no_fees"])
k5, k6, k7, k8 = st.columns(4)
k5.metric("Collected so far", rupees(summary["collected_paise"]))
k6.metric("Overdue now", rupees(summary["overdue_paise"]))
k7.metric("Still to collect this term", rupees(summary["remaining_paise"]))
k8.metric("Expected for term", rupees(summary["expected_paise"]))

tab_trend, tab_defaulters, tab_breakdown, tab_compare, tab_range = st.tabs(
    ["Trends", "Not paid", "Breakdowns", "Term comparison", "Custom date range"])

with tab_trend:
    trend = report_service.monthly_trend(report_filter)
    st.markdown("##### Fees due vs paid, by fee month")
    st.bar_chart(trend.set_index("Month")[["Due", "Paid against month"]], stack=False, x_label="", y_label="₹")
    st.markdown("##### Money collected, by payment month")
    st.line_chart(trend.set_index("Month")[["Collected in month"]], x_label="", y_label="₹")

with tab_defaulters:
    defaulters = report_service.defaulters(report_filter)
    st.markdown(f"##### {len(defaulters)} students with overdue fees in {term.label} (as of {as_of:%d %b %Y})")
    if defaulters.empty:
        st.success("Nobody has overdue fees for this selection.")
    else:
        st.dataframe(defaulters, hide_index=True, width="stretch",
                     column_config={c: st.column_config.NumberColumn(format="₹%.2f")
                                    for c in ("Overdue (Rs)", "Balance for year (Rs)")})
        school = settings_service.get_settings()[settings_service.SCHOOL_NAME]
        st.download_button(
            "Download as Excel",
            build_workbook({"Not paid": defaulters}, f"Overdue fees {term.label} as of {as_of:%d-%m-%Y}", school,
                           money_columns=report_service.MONEY_COLUMNS),
            file_name=f"overdue_{term.label}_{as_of:%Y%m%d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

with tab_breakdown:
    left, right = st.columns(2)
    classes = report_service.class_breakdown(report_filter)
    with left:
        st.markdown("##### By class")
        if classes.empty:
            st.caption("No data.")
        else:
            st.bar_chart(classes.set_index("Class")[["Paid", "Overdue"]], x_label="", y_label="₹")
            st.dataframe(classes, hide_index=True, width="stretch")
    with right:
        st.markdown("##### By payment mode")
        methods = report_service.payment_method_split(report_filter)
        st.dataframe(methods, hide_index=True, width="stretch")
        st.markdown("##### By category")
        st.dataframe(report_service.category_breakdown(report_filter), hide_index=True, width="stretch")

with tab_compare:
    comparison = report_service.term_comparison()
    if len(comparison) < 2:
        st.caption("Comparison appears once there is more than one term.")
    st.bar_chart(comparison.set_index("Term")[["Due", "Paid", "Outstanding"]], stack=False, x_label="", y_label="₹")
    st.dataframe(comparison, hide_index=True, width="stretch")

with tab_range:
    r1, r2 = st.columns(2)
    date_from = r1.date_input("From", value=today_ist() - timedelta(days=30), format="DD/MM/YYYY", key="sum_from")
    date_to = r2.date_input("To", value=today_ist(), format="DD/MM/YYYY", key="sum_to")
    if date_from > date_to:
        st.error("'From' must be before 'To'.")
    else:
        range_filter = ReportFilter(academic_year_id=term.id, student_class=student_class, section=section,
                                    category=category)
        sheets = report_service.custom_report(date_from, date_to, range_filter)
        payments = sheets["Payments"]
        st.metric("Collected in range", rupees(int(round(payments["Amount (Rs)"].sum() * 100))) if len(payments) else rupees(0))
        st.dataframe(sheets["By fee type"], hide_index=True)
        st.dataframe(payments, hide_index=True, width="stretch")
