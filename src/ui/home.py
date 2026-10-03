import streamlit as st

from data_management.services import academic_year_service, payment_service, report_service, settings_service
from data_management.services.report_service import ReportFilter
from helper.clock import today_ist
from ui.common import page_header, require_user, rupees

user = require_user()
school = settings_service.get_settings()
page_header(school[settings_service.SCHOOL_NAME], f"Fee tracker · {today_ist():%A, %d %B %Y}")

year = academic_year_service.get_current_year()
if year is None:
    st.warning("No current term is set. An administrator can set one in Admin > Terms & fees.")
    st.stop()

summary = report_service.dashboard(ReportFilter(academic_year_id=year.id))
st.subheader(f"Term {year.label}")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Collected today", rupees(summary["collected_today_paise"]))
c2.metric("Collected this month", rupees(summary["collected_this_month_paise"]))
c3.metric("Overdue now", rupees(summary["overdue_paise"]))
c4.metric("Students with dues", f"{summary['defaulters']} of {summary['enrolled']}")
if summary["no_fees"]:
    st.info(f"{summary['no_fees']} enrolled students have no fees set - add the class fee in "
            "Admin > Terms & fees and apply it.")

st.markdown("#### Quick actions")
q1, q2, q3, q4 = st.columns(4)
q1.page_link("ui/billing/billing.py", label="Collect fees", icon="💵")
q2.page_link("ui/student/students.py", label="Add / find students", icon="🧑‍🎓")
q3.page_link("ui/analytics/summary.py", label="Who has not paid", icon="📊")
q4.page_link("ui/reports/reports.py", label="Excel reports", icon="📑")

st.markdown("#### Latest receipts")
recent = payment_service.list_payments(limit=10)
if recent:
    st.dataframe(
        [{"Receipt": p.receipt_no, "Date": p.paid_on, "Student": p.student_name,
          "Class": f"{p.student_class}-{p.section}", "Amount": rupees(p.amount_paise), "Mode": p.payment_method,
          "Status": "VOID" if p.is_voided else ""} for p in recent],
        hide_index=True, width="stretch")
else:
    st.caption("No receipts yet.")
