import pandas as pd
import streamlit as st

from data_management.dto.academic_year import AcademicYearCreate
from data_management.dto.promotion import DECISION_OUTCOMES, PromotionDecision, PromotionRequest
from data_management.services import academic_year_service, promotion_service
from statics import CLASSES, SECTIONS
from ui.common import flash, optional_select, page_header, require_user, run_action, term_select

user = require_user(admin_only=True)
page_header("Promotion", "Close a term for a class and move students into the next term.")

years = academic_year_service.list_years()
c1, c2, c3, c4 = st.columns(4)
with c1:
    from_term = term_select("From term", key="promo_from", years=years)
later = [y for y in years if from_term and y.start_date > from_term.start_date]
with c2:
    if later:
        to_term = st.selectbox("To term", sorted(later, key=lambda y: y.start_date), format_func=lambda y: y.label)
    else:
        to_term = None
        st.write("")
        if from_term and st.button(f"Create term {from_term.start_date.year + 1}-{(from_term.start_date.year + 2) % 100:02d}"):
            if run_action(academic_year_service.create_year, AcademicYearCreate(start_year=from_term.start_date.year + 1)):
                st.rerun()
student_class = c3.selectbox("Class", CLASSES, key="promo_class")
with c4:
    section = optional_select("Section", SECTIONS, key="promo_section")

if not (from_term and to_term):
    st.info("Choose (or create) the term to promote into.")
    st.stop()

candidates = promotion_service.candidates(from_term.id, student_class, section)
if not candidates:
    st.success(f"No open {student_class} enrollments in {from_term.label} for this selection - already promoted, "
               "or nobody enrolled.")
    st.stop()

final_class = candidates[0].next_class is None
st.caption(("Class 10 students marked PROMOTED will be recorded as PASSED OUT. " if final_class else "")
           + "Each student gets the new term's default tuition plan for their class and category. "
             "Van is not carried over; assign it again in the new term.")
table = pd.DataFrame({
    "Roll": [c.roll_no for c in candidates], "Name": [c.name for c in candidates],
    "Admission no": [c.admission_no for c in candidates],
    "Now": [f"{c.student_class}-{c.section}" for c in candidates],
    "Next class": [c.next_class or "Passed out" for c in candidates],
    "Outcome": ["PROMOTED"] * len(candidates),
    "New section": [c.section for c in candidates],
    "enrollment_id": [c.enrollment_id for c in candidates],
})
edited = st.data_editor(table, hide_index=True, width="stretch",
                        disabled=["Roll", "Name", "Admission no", "Now", "Next class"],
                        key=f"promo_editor_{from_term.id}_{student_class}_{section}",
                        column_config={
                            "Outcome": st.column_config.SelectboxColumn(options=DECISION_OUTCOMES, required=True),
                            "New section": st.column_config.SelectboxColumn(options=SECTIONS, required=True),
                            "enrollment_id": None,
                        })
counts = edited["Outcome"].value_counts().to_dict()
st.markdown(" · ".join(f"**{k.title()}**: {v}" for k, v in counts.items()))


KEY_PENDING = "promo_pending_request"


def discard() -> None:
    st.session_state.pop(KEY_PENDING, None)


@st.dialog("Confirm promotion", on_dismiss=discard)
def confirm() -> None:
    request: PromotionRequest = st.session_state[KEY_PENDING]
    st.write(f"Close {len(request.decisions)} {student_class} enrollments in {from_term.label} and "
             f"open them in {to_term.label}. This cannot be undone from the app.")
    if st.button("Promote now", type="primary"):
        result = run_action(promotion_service.promote, request)
        discard()
        if result:
            flash(f"Done: {result.promoted} promoted, {result.retained} retained, {result.left} left, "
                  f"{result.passed_out} passed out.")
            st.rerun()


if st.button("Run promotion", type="primary"):
    request = run_action(lambda: PromotionRequest(from_year_id=from_term.id, to_year_id=to_term.id, decisions=[
        PromotionDecision(enrollment_id=int(row["enrollment_id"]), outcome=row["Outcome"],
                          target_section=row["New section"]) for row in edited.to_dict("records")]))
    if request:
        st.session_state[KEY_PENDING] = request

pending = st.session_state.get(KEY_PENDING)
if pending and pending.from_year_id == from_term.id and pending.to_year_id == to_term.id:
    confirm()
elif pending:
    discard()
