import uuid
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

from data_management.dto.fee import FeeAssignment, FeeDueRead, OneOffDueCreate, fee_type_label
from data_management.dto.payment import AllocationInput, PaymentCreate, VoidRequest
from data_management.dto.student import EnrollmentRead, StudentProfile, StudentSearch
from data_management.services import academic_year_service, fee_service, payment_service, student_service
from data_management.services.identifier_crypto import mask
from helper import fee_rules
from helper.clock import today_ist
from helper.money import amount_in_words_inr, rupees_to_paise
from reports.receipt import render_receipt_html
from statics import (
    CLASSES,
    FEE_TYPE_LABELS,
    ONE_OFF_FEE_TYPES,
    PAYMENT_METHODS,
    RECEIPT_SOFT_LIMIT,
    SECTIONS,
    FeeType,
)
from ui.common import flash, optional_select, page_header, require_user, run_action, rupee_input, rupees, term_select

KEY_STUDENT = "bill_student_id"
KEY_YEAR = "bill_year_id"
KEY_PREFILL = "bill_prefill"
KEY_EDITOR_VERSION = "bill_editor_version"
KEY_LAST_RECEIPT = "bill_last_receipt_id"
KEY_PENDING_TOKEN = "bill_pending_token"
KEY_DONE_TOKENS = "bill_done_tokens"
KEY_PENDING_REQUEST = "bill_pending_request"

user = require_user()
page_header("Collect fees", "Find a student, enter what is being paid now, then issue the receipt.")
years = {year.id: year for year in academic_year_service.list_years()}


def reset_editor(prefill: Optional[Dict[int, int]] = None) -> None:
    st.session_state[KEY_PREFILL] = prefill or {}
    st.session_state[KEY_EDITOR_VERSION] = st.session_state.get(KEY_EDITOR_VERSION, 0) + 1


def select_student(student_id: int, year_id: Optional[int] = None) -> None:
    st.session_state.pop(KEY_PENDING_REQUEST, None)
    st.session_state[KEY_STUDENT] = student_id
    if year_id:
        st.session_state[KEY_YEAR] = year_id
    st.session_state.pop(KEY_LAST_RECEIPT, None)
    reset_editor()


def clear_student() -> None:
    for key in (KEY_STUDENT, KEY_YEAR, KEY_LAST_RECEIPT, KEY_PENDING_REQUEST):
        st.session_state.pop(key, None)
    reset_editor()


# ---------------------------------------------------------------- search
def search_panel() -> None:
    mode = st.radio("Search by", ["Student ID / admission no", "Name and class"], horizontal=True,
                    key="bill_search_mode")
    if mode.startswith("Student ID"):
        with st.form("bill_find_id"):
            value = st.text_input("Student ID or admission number", placeholder="e.g. 42 or ADM/2026-27/0042")
            found = st.form_submit_button("Find", type="primary")
        if found and value.strip():
            profile = run_action(student_service.find_by_id_or_admission_no, value)
            if profile:
                select_student(profile.student_id)
                st.rerun()
            st.error(f"No student found for '{value.strip()}'.")
        return

    c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
    name = c1.text_input("Name, admission no or guardian mobile", key="bill_search_text")
    with c2:
        term = term_select(key="bill_search_term", years=list(years.values()))
    with c3:
        student_class = optional_select("Class", CLASSES, key="bill_search_class")
    with c4:
        section = optional_select("Section", SECTIONS, key="bill_search_section")
    if term is None:
        return
    if not (name.strip() or student_class):
        st.caption("Type part of a name, or choose a class, to list students.")
        return
    results = student_service.search_students(StudentSearch(text=name, academic_year_id=term.id,
                                                            student_class=student_class, section=section))
    if not results:
        st.caption("No matching students.")
        return
    table = pd.DataFrame([{
        "ID": r.student_id, "Admission no": r.admission_no, "Name": r.name,
        "Class": f"{r.student_class}-{r.section}", "Roll": r.roll_no, "Guardian": r.guardian_name,
        "Mobile": r.guardian_mobile, "Status": r.status} for r in results])
    st.caption("Click a row to select the student.")
    event = st.dataframe(table, hide_index=True, width="stretch", on_select="rerun",
                         selection_mode="single-row", key="bill_search_results")
    if event.selection.rows:
        chosen = results[event.selection.rows[0]]
        if chosen.student_id != st.session_state.get(KEY_STUDENT):
            select_student(chosen.student_id, term.id)
            st.rerun()


with st.expander("Find student", expanded=KEY_STUDENT not in st.session_state):
    search_panel()

student_id = st.session_state.get(KEY_STUDENT)
if not student_id:
    st.info("Search for a student to begin.")
    st.stop()

profile: StudentProfile = run_action(student_service.get_profile, student_id)
if profile is None:
    clear_student()
    st.stop()


# ---------------------------------------------------------------- student card
def choose_enrollment() -> Optional[EnrollmentRead]:
    if not profile.enrollments:
        st.warning("This student is not enrolled in any term. Enrol them from the Students page.")
        return None
    current = next((y.id for y in years.values() if y.is_current), None)
    wanted = st.session_state.get(KEY_YEAR) or current
    index = next((i for i, e in enumerate(profile.enrollments) if e.academic_year_id == wanted), 0)
    return st.selectbox(
        "Term", profile.enrollments, index=index, key=f"bill_term_{profile.student_id}",
        format_func=lambda e: f"{e.academic_year_label} - Class {e.class_section}"
                              + (f", roll {e.roll_no}" if e.roll_no else ""))


with st.container(border=True):
    head, action = st.columns([4, 1])
    head.subheader(profile.name)
    head.caption(f"Student ID {profile.student_id} · Admission no {profile.admission_no} · "
                 f"{profile.category or 'Category not set'} · {profile.status.replace('_', ' ').title()}")
    if action.button("Change student", width="stretch"):
        clear_student()
        st.rerun()
    left, middle, right = st.columns([2, 2, 1])
    with left:
        enrollment = choose_enrollment()
    guardian = profile.primary_guardian
    middle.markdown(f"**Guardian:** {guardian.name} ({guardian.relation_type.title()})  \n"
                    f"**Mobile:** {guardian.mobile_number or '-'}" if guardian else "**Guardian:** not added")
    right.markdown(f"**Aadhaar:** {mask(profile.identifier_last_4)}")

if enrollment is None:
    st.stop()
if st.session_state.get(KEY_YEAR) != enrollment.academic_year_id:
    st.session_state[KEY_YEAR] = enrollment.academic_year_id
    reset_editor()

year = years[enrollment.academic_year_id]
ledger: List[FeeDueRead] = fee_service.get_ledger(enrollment.enrollment_id)
status = fee_service.payment_status(enrollment.enrollment_id)
expected_percent = status["expected_percent"]


def overdue_of(due: FeeDueRead) -> int:
    if due.is_annual:
        return fee_rules.overdue_amount(due.amount_due_paise, due.amount_paid_paise, expected_percent)
    return due.balance_paise if due.created_on <= status["as_of"] else 0


# ---------------------------------------------------------------- receipt just saved
last_receipt_id = st.session_state.get(KEY_LAST_RECEIPT)
if last_receipt_id:
    receipt = run_action(payment_service.get_payment, last_receipt_id)
    if receipt:
        with st.container(border=True):
            st.success(f"Receipt **{receipt.receipt_no}** saved for {rupees(receipt.amount_paise)} "
                       f"({receipt.amount_in_words}).")
            st.download_button("Download / print receipt", render_receipt_html(receipt),
                               file_name=f"{receipt.receipt_no.replace('/', '-')}.html", mime="text/html",
                               type="primary", key="bill_download_last")

# ---------------------------------------------------------------- dues summary
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Fees for term", rupees(sum(d.amount_due_paise for d in ledger)))
m2.metric("Paid", rupees(sum(d.amount_paid_paise for d in ledger)))
m3.metric("Balance", rupees(sum(d.balance_paise for d in ledger)))
m4.metric(f"Expected by now ({expected_percent}%)", rupees(status["expected_paise"]))
m5.metric("Overdue", rupees(status["overdue_paise"]))

notes = []
if status["next_milestone"]:
    due_date, percent = status["next_milestone"]
    notes.append(f"Next milestone: {percent}% of annual fees by {due_date:%d %b %Y}.")
elif not status["has_milestones"]:
    notes.append("No payment milestones are set for this term, so fees become overdue only at the end of the term.")
receipts_used = status["receipts"]
if receipts_used >= RECEIPT_SOFT_LIMIT:
    st.warning(f"{receipts_used} receipts already issued this term - more than the usual {RECEIPT_SOFT_LIMIT} "
               "instalments. Another receipt is allowed, but check with the office if this is expected.")
else:
    notes.append(f"Instalments this term: {receipts_used} of {RECEIPT_SOFT_LIMIT}.")
st.caption(" ".join(notes))

if not any(d.fee_type == FeeType.TUITION.value for d in ledger):
    st.warning("No tuition fee is assigned to this student for this term. "
               + ("Assign one under 'Fee plan & van' below." if user.is_admin
                  else "Ask an administrator to assign a fee plan."))

if ledger:
    st.dataframe(pd.DataFrame([{
        "Fee": d.label, "Amount": rupees(d.amount_due_paise), "Paid": rupees(d.amount_paid_paise),
        "Balance": rupees(d.balance_paise), "Overdue": rupees(overdue_of(d)) if overdue_of(d) else "",
        "Status": d.status, "Note": d.override_reason or ""} for d in ledger]), hide_index=True, width="stretch")

# ---------------------------------------------------------------- collect payment
st.markdown("### Collect payment")
open_dues = [d for d in ledger if d.balance_paise > 0]


def discard_pending() -> None:
    st.session_state.pop(KEY_PENDING_REQUEST, None)


@st.dialog("Confirm receipt", on_dismiss=discard_pending)
def confirm_payment() -> None:
    request, lines = st.session_state[KEY_PENDING_REQUEST]
    st.markdown(f"**{profile.name}** · {enrollment.academic_year_label} · Class {enrollment.class_section}")
    st.markdown("\n".join(f"- {line}" for line in lines))
    st.markdown(f"**Total: {rupees(request.amount_paise)}**  \n{amount_in_words_inr(request.amount_paise)}")
    st.markdown(f"Mode: {request.payment_method} · Date: {request.paid_on:%d %b %Y} · From: {request.billing_name}")
    save_col, cancel_col = st.columns(2)
    if cancel_col.button("Cancel", width="stretch"):
        discard_pending()
        st.rerun()
    if save_col.button("Confirm and save receipt", type="primary", width="stretch"):
        token = st.session_state.get(KEY_PENDING_TOKEN)
        done = st.session_state.setdefault(KEY_DONE_TOKENS, set())
        if token in done:
            discard_pending()
            st.warning("This receipt was already saved.")
            return
        receipt = run_action(payment_service.create_payment, request, user.username)
        if receipt:
            done.add(token)
            discard_pending()
            st.session_state[KEY_LAST_RECEIPT] = receipt.id
            reset_editor()
            flash(f"Receipt {receipt.receipt_no} saved.")
            st.rerun()


if not open_dues:
    st.success("Nothing is pending for this term.")
else:
    with st.container(border=True):
        q1, q2, q3 = st.columns([2, 3, 1.4])
        with q1:
            quick_amount = rupee_input("Amount received", key=f"bill_quick_amount_{enrollment.enrollment_id}")
        fee_types = sorted({d.fee_type for d in open_dues}, key=lambda t: list(FeeType).index(FeeType(t)))
        quick_types = q2.multiselect("Apply to (optional)", fee_types, key=f"bill_quick_types_{enrollment.enrollment_id}",
                                     format_func=lambda t: FEE_TYPE_LABELS[FeeType(t)],
                                     placeholder="All pending fees")
        q3.write("")
        q3.write("")
        if q3.button("Fill in order", width="stretch", disabled=quick_amount <= 0,
                     help="Tuition first, then van, then other fees"):
            suggestion = payment_service.suggest_allocation(open_dues, quick_amount, quick_types or None)
            reset_editor({a.fee_due_id: a.amount_paise for a in suggestion})
            st.rerun()

        prefill = st.session_state.get(KEY_PREFILL, {})
        table = pd.DataFrame({
            "Pay": [d.fee_due_id in prefill for d in open_dues],
            "Fee": [d.label + (f" (overdue {rupees(overdue_of(d))})" if overdue_of(d) else "") for d in open_dues],
            "Pending (₹)": [d.balance_paise / 100 for d in open_dues],
            "Pay now (₹)": [prefill.get(d.fee_due_id, 0) / 100 for d in open_dues],
            "fee_due_id": [d.fee_due_id for d in open_dues],
        })
        st.caption("Tick a fee to pay its full balance, or type any smaller amount in **Pay now** - parents can pay "
                   "in instalments whenever they are able to.")
        edited = st.data_editor(
            table, hide_index=True, width="stretch", disabled=["Fee", "Pending (₹)"],
            key=f"bill_editor_{enrollment.enrollment_id}_{st.session_state.get(KEY_EDITOR_VERSION, 0)}",
            column_config={
                "Pay": st.column_config.CheckboxColumn("Pay", width="small"),
                "Pay now (₹)": st.column_config.NumberColumn("Pay now (₹)", min_value=0.0, step=1.0, format="%.2f"),
                "fee_due_id": None,
            },
        )

        allocations: List[AllocationInput] = []
        lines: List[str] = []
        problems: List[str] = []
        dues_by_id = {d.fee_due_id: d for d in open_dues}
        for row in edited.to_dict("records"):
            due = dues_by_id[int(row["fee_due_id"])]
            typed = rupees_to_paise(row["Pay now (₹)"] or 0)
            if not row["Pay"] and typed == 0:
                continue
            amount = typed or due.balance_paise
            if amount > due.balance_paise:
                problems.append(f"{due.label}: only {rupees(due.balance_paise)} is pending")
                continue
            allocations.append(AllocationInput(fee_due_id=due.fee_due_id, amount_paise=amount))
            lines.append(f"{due.label}: {rupees(amount)}")
        for problem in problems:
            st.error(problem)
        total = sum(a.amount_paise for a in allocations)
        if quick_amount and allocations and total != quick_amount:
            st.warning(f"Selected fees total {rupees(total)}, but the amount received is {rupees(quick_amount)}.")
        st.markdown(f"**Total: {rupees(total)}**" + (f" — {amount_in_words_inr(total)}" if total else ""))

        d1, d2, d3 = st.columns(3)
        suffix = enrollment.enrollment_id
        billing_name = d1.text_input("Received from", value=guardian.name if guardian else "", key=f"bill_name_{suffix}")
        paid_on = d2.date_input("Payment date", value=today_ist(), max_value=today_ist(), format="DD/MM/YYYY",
                                key=f"bill_date_{suffix}")
        method = d3.selectbox("Mode", PAYMENT_METHODS, key=f"bill_method_{suffix}")
        e1, e2 = st.columns(2)
        reference = e1.text_input("Reference (UPI / card transaction no)", key=f"bill_ref_{suffix}")
        notes = e2.text_input("Notes", key=f"bill_notes_{suffix}")

        if st.button("Review and save receipt", type="primary", disabled=not allocations or bool(problems)):
            request = run_action(lambda: PaymentCreate(
                student_id=profile.student_id, enrollment_id=enrollment.enrollment_id, paid_on=paid_on,
                payment_method=method, billing_name=billing_name, payment_notes=reference, notes=notes,
                allocations=allocations))
            if request:
                st.session_state[KEY_PENDING_TOKEN] = uuid.uuid4().hex
                st.session_state[KEY_PENDING_REQUEST] = (request, lines)

pending = st.session_state.get(KEY_PENDING_REQUEST)
if pending and pending[0].enrollment_id == enrollment.enrollment_id:
    confirm_payment()
elif pending:
    discard_pending()

# ---------------------------------------------------------------- manage fees
one_off = [d for d in ledger if not d.is_annual]


def assign_annual(fee_type: str, prefix: str) -> None:
    """Plan / custom amount picker for an annual fee (radio outside the form so it reacts immediately)."""
    current = next((d for d in ledger if d.fee_type == fee_type), None)
    if current:
        st.caption(f"Current: {current.label} - {rupees(current.amount_due_paise)} "
                   f"(paid {rupees(current.amount_paid_paise)})")
    mode = st.radio("Set", ["Fee plan", "Custom amount"], horizontal=True, key=f"{prefix}_mode")
    with st.form(f"{prefix}_form_{enrollment.enrollment_id}"):
        if mode == "Fee plan":
            plans = fee_service.list_plans(year.id, fee_type=fee_type, active_only=True)
            if fee_type == FeeType.TUITION.value:
                plans = [p for p in plans if p.student_class == enrollment.student_class]
            picked = st.selectbox("Plan", plans, format_func=lambda p: f"{p.code} - {rupees(p.annual_amount_paise)}"
                                  + (f" ({p.description})" if p.description else ""))
            custom, reason = None, None
        else:
            picked = None
            custom = rupee_input("Annual amount", key=f"{prefix}_custom_{enrollment.enrollment_id}",
                                 value_paise=current.amount_due_paise if current else 0)
            reason = st.text_input("Reason (required)")
        if st.form_submit_button(f"Save {fee_type_label(fee_type).lower()}"):
            if mode == "Fee plan" and picked is None:
                st.error(f"No active {fee_type_label(fee_type).lower()} plan fits this student in {year.label}.")
            else:
                data = run_action(lambda: FeeAssignment(
                    enrollment_id=enrollment.enrollment_id, fee_type=fee_type,
                    fee_plan_id=picked.id if picked else None, custom_amount_paise=custom, reason=reason))
                if data and run_action(fee_service.assign, data):
                    flash(f"{fee_type_label(fee_type)} updated.")
                    reset_editor()
                    st.rerun()


with st.expander("Fee plan & van" if user.is_admin else "Van & other fees"):
    left, right = st.columns(2)
    with left:
        st.markdown("**Van fee** (annual, paid in instalments like tuition)")
        assign_annual(FeeType.VAN.value, "bill_van")
        if any(d.fee_type == FeeType.VAN.value for d in ledger) and st.button("Stop van"):
            result = run_action(fee_service.remove_van, enrollment.enrollment_id)
            if result is not None:
                flash("Van removed." if result["removed"] else "Van stopped; the fee is reduced to what was paid.")
                reset_editor()
                st.rerun()
    with right:
        if user.is_admin:
            st.markdown("**Tuition fee plan**")
            assign_annual(FeeType.TUITION.value, "bill_tuition")
        st.markdown("**Add a one-off fee** (books, uniform, ...)")
        with st.form(f"bill_add_fee_{enrollment.enrollment_id}", clear_on_submit=True):
            fee_type = st.selectbox("Fee", [t.value for t in ONE_OFF_FEE_TYPES],
                                    format_func=lambda t: FEE_TYPE_LABELS[FeeType(t)])
            description = st.text_input("Description (required for Custom fee)")
            amount = rupee_input("Amount", key=f"bill_add_amount_{enrollment.enrollment_id}")
            if st.form_submit_button("Add fee"):
                data = run_action(lambda: OneOffDueCreate(enrollment_id=enrollment.enrollment_id, fee_type=fee_type,
                                                          description=description, amount_paise=amount))
                if data and run_action(fee_service.add_one_off_due, data):
                    flash(f"{FEE_TYPE_LABELS[FeeType(fee_type)]} of {rupees(amount)} added.")
                    reset_editor()
                    st.rerun()
        removable = [d for d in one_off if d.amount_paid_paise == 0]
        if removable:
            target = st.selectbox("Remove an unpaid fee", removable, format_func=lambda d: d.label,
                                  key=f"bill_remove_fee_{enrollment.enrollment_id}")
            if st.button("Remove fee"):
                if run_action(lambda: fee_service.remove_due(target.fee_due_id) or True):
                    flash(f"Removed {target.label}.")
                    reset_editor()
                    st.rerun()

# ---------------------------------------------------------------- receipts
with st.expander("Receipts for this term", expanded=False):
    receipts = payment_service.list_payments(enrollment_id=enrollment.enrollment_id)
    if not receipts:
        st.caption("No receipts yet.")
    else:
        st.dataframe(pd.DataFrame([{
            "Receipt": p.receipt_no, "Date": p.paid_on, "Amount": rupees(p.amount_paise), "Mode": p.payment_method,
            "For": ", ".join(a.label for a in p.allocations), "Status": "VOID" if p.is_voided else "",
            "By": p.collected_by} for p in receipts]), hide_index=True, width="stretch")
        chosen = st.selectbox("Receipt", receipts, format_func=lambda p: f"{p.receipt_no} - {rupees(p.amount_paise)}"
                              + (" (VOID)" if p.is_voided else ""), key=f"bill_receipt_pick_{enrollment.enrollment_id}")
        st.download_button("Download receipt", render_receipt_html(chosen),
                           file_name=f"{chosen.receipt_no.replace('/', '-')}.html", mime="text/html",
                           key=f"bill_receipt_download_{chosen.id}")
        if user.is_admin and not chosen.is_voided:
            with st.form(f"bill_void_{chosen.id}", clear_on_submit=True):
                reason = st.text_input("Reason for voiding this receipt")
                if st.form_submit_button("Void receipt"):
                    if run_action(payment_service.void_payment, VoidRequest(payment_id=chosen.id, reason=reason),
                                  user.username):
                        flash(f"Receipt {chosen.receipt_no} voided; its fees are pending again.", "warning")
                        reset_editor()
                        st.rerun()
