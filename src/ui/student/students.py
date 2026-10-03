from typing import Optional

import pandas as pd
import streamlit as st

from data_management.dto.guardian import GuardianLinkInput
from data_management.dto.student import (
    EnrollmentUpdate,
    IdentifierInput,
    StudentCreate,
    StudentLeaving,
    StudentProfile,
    StudentSearch,
    StudentUpdate,
)
from data_management.services import academic_year_service, guardian_service, student_service
from data_management.services.identifier_crypto import mask
from helper.clock import today_ist
from statics import CLASSES, GUARDIAN_TYPES, SECTIONS, STUDENT_CATEGORY, StudentStatus
from ui.common import flash, optional_select, page_header, require_user, run_action, rupee_input, term_select

KEY_SELECTED = "stu_selected_id"

user = require_user()
page_header("Students")
years = academic_year_service.list_years()
current_year = next((y for y in years if y.is_current), years[0] if years else None)
if current_year is None:
    st.warning("Create an academic year first (Admin > Terms & fees).")
    st.stop()


def index_of(options, value) -> Optional[int]:
    return options.index(value) if value in options else None


GUARDIAN_NEW = "New guardian"
GUARDIAN_EXISTING = "Existing guardian"
GUARDIAN_SKIP = "Skip for now"


def guardian_mode_selector(prefix: str, allow_skip: bool = True) -> str:
    """
    Must be called OUTSIDE a form: widgets inside st.form do not rerun the page
    until submit, so the guardian fields could not react to this choice.
    """
    options = [GUARDIAN_NEW, GUARDIAN_EXISTING] + ([GUARDIAN_SKIP] if allow_skip else [])
    return st.radio("Guardian", options, horizontal=True, key=f"{prefix}_guardian_mode")


def guardian_picker(prefix: str, mode: str):
    """Guardian fields for the chosen mode (call inside the form). Returns a GuardianLinkInput-ready dict or None."""
    if mode == GUARDIAN_SKIP:
        st.caption("No guardian will be linked now; you can add one later from Find & manage → Guardians.")
        return None
    relation = st.selectbox("Relation", GUARDIAN_TYPES, key=f"{prefix}_relation")
    if mode == GUARDIAN_EXISTING:
        guardians = guardian_service.list_guardians()
        picked = st.selectbox("Choose guardian", guardians, index=None, key=f"{prefix}_existing",
                              format_func=lambda g: f"{g.name} ({g.mobile_number or 'no mobile'})"
                                                    + (f" - {', '.join(g.students)}" if g.students else ""))
        return {"guardian_id": picked.id if picked else -1, "relation_type": relation}
    g1, g2, g3 = st.columns(3)
    name = g1.text_input("Guardian name", key=f"{prefix}_g_name")
    mobile = g2.text_input("Mobile", key=f"{prefix}_g_mobile")
    yob = g3.number_input("Year of birth (optional)", min_value=0, max_value=today_ist().year, value=0,
                          key=f"{prefix}_g_yob")
    if not name.strip():
        return {"missing_name": True}
    return {"new_guardian": {"name": name, "mobile_number": mobile, "year_of_birth": yob or None},
            "relation_type": relation}


def manage_student(profile: StudentProfile) -> None:

    st.divider()
    st.subheader(f"{profile.name}")
    st.caption(f"Student ID {profile.student_id} · Admission no {profile.admission_no} · "
               f"{profile.status.replace('_', ' ').title()}"
               + (f" · left on {profile.date_of_leaving:%d %b %Y}" if profile.date_of_leaving else ""))
    if profile.notes:
        st.info(profile.notes)
    pid = profile.student_id
    t_details, t_class, t_aadhaar, t_guardians, t_status = st.tabs(
        ["Details", "Class & roll", "Aadhaar", "Guardians", "Status"])

    with t_details:
        with st.form(f"stu_edit_{pid}"):
            e1, e2, e3 = st.columns(3)
            e_name = e1.text_input("Full name", value=profile.name)
            e_adm = e2.text_input("Admission number", value=profile.admission_no)
            e_cat = e3.selectbox("Category", STUDENT_CATEGORY, index=index_of(STUDENT_CATEGORY, profile.category))
            e4, e5, e6 = st.columns(3)
            e_dob = e4.date_input("Date of birth", value=profile.date_of_birth, format="DD/MM/YYYY",
                                  min_value=today_ist().replace(year=today_ist().year - 30), max_value=today_ist())
            e_join = e5.date_input("Date of joining", value=profile.date_of_join, format="DD/MM/YYYY",
                                   max_value=today_ist())
            e_joined = e6.selectbox("Class joined", CLASSES, index=index_of(CLASSES, profile.class_joined))
            e_notes = st.text_input("Notes", value=profile.notes or "")
            if st.form_submit_button("Save details", type="primary"):
                update = run_action(lambda: StudentUpdate(
                    name=e_name, admission_no=e_adm, category=e_cat, date_of_birth=e_dob, date_of_join=e_join,
                    class_joined=e_joined, notes=e_notes))
                if update and run_action(student_service.update_student, pid, update):
                    flash("Details saved.")
                    st.rerun()

    with t_class:
        st.dataframe(pd.DataFrame([{"Term": e.academic_year_label, "Class": e.class_section, "Roll": e.roll_no,
                                    "Outcome": e.outcome or "In progress"} for e in profile.enrollments]),
                     hide_index=True, width="stretch")
        manage_term = term_select("Term to manage", key=f"stu_class_term_{pid}", years=years)
        enrollment = profile.enrollment_for(manage_term.id) if manage_term else None
        if enrollment:
            with st.form(f"stu_roll_{pid}_{enrollment.enrollment_id}"):
                r1, r2 = st.columns(2)
                new_section = r1.selectbox("Section", SECTIONS, index=index_of(SECTIONS, enrollment.section) or 0)
                new_roll = r2.number_input("Roll no (0 = none)", min_value=0, value=enrollment.roll_no or 0)
                if st.form_submit_button("Save section / roll"):
                    data = run_action(lambda: EnrollmentUpdate(section=new_section, roll_no=new_roll or None))
                    if data and run_action(lambda: student_service.update_enrollment(
                            enrollment.enrollment_id, data) or True):
                        flash("Section and roll number saved.")
                        st.rerun()
            if user.is_admin:
                with st.form(f"stu_class_fix_{enrollment.enrollment_id}"):
                    st.caption("Correct a wrongly entered class (only possible before any tuition is paid).")
                    fixed = st.selectbox("Correct class", CLASSES, index=index_of(CLASSES, enrollment.student_class))
                    if st.form_submit_button("Change class"):
                        if run_action(lambda: student_service.change_class(enrollment.enrollment_id, fixed) or True):
                            flash(f"Class changed to {fixed}; tuition fees regenerated.")
                            st.rerun()
        elif manage_term:
            st.info(f"Not enrolled in {manage_term.label}.")
            with st.form(f"stu_enroll_{pid}_{manage_term.id}"):
                n1, n2, n3 = st.columns(3)
                enrol_class = n1.selectbox("Class", CLASSES, index=None)
                enrol_section = n2.selectbox("Section", SECTIONS)
                enrol_roll = n3.number_input("Roll no (0 = later)", min_value=0, value=0)
                if st.form_submit_button(f"Enrol in {manage_term.label}"):
                    if enrol_class is None:
                        st.error("Choose a class.")
                    elif run_action(student_service.enroll_existing_student, pid, manage_term.id, enrol_class,
                                    enrol_section, enrol_roll or None):
                        flash(f"Enrolled in {manage_term.label}.")
                        st.rerun()

    with t_aadhaar:
        st.markdown(f"Stored: **{mask(profile.identifier_last_4)}** "
                    + ("(full number encrypted)" if profile.has_full_identifier else "(last 4 digits only)"))
        if user.is_admin and profile.has_full_identifier:
            if st.button("Show full number", key=f"stu_reveal_{pid}"):
                number = run_action(student_service.reveal_identifier, pid, user.username)
                if number:
                    st.code(f"{number[:4]} {number[4:8]} {number[8:]}")
                    st.caption("Shown once; this view is logged.")
        with st.form(f"stu_aadhaar_{pid}", clear_on_submit=True):
            i1, i2 = st.columns(2)
            new_full = i1.text_input("Full Aadhaar number")
            new_last4 = i2.text_input("...or last 4 digits", max_chars=4)
            if st.form_submit_button("Save Aadhaar"):
                data = run_action(lambda: IdentifierInput(full_number=new_full, last_4_digits=new_last4))
                if data and run_action(lambda: student_service.update_identifier(pid, data) or True):
                    flash("Aadhaar saved.")
                    st.rerun()

    with t_guardians:
        for link in profile.guardians:
            g1, g2, g3, g4 = st.columns([3, 2, 1.2, 1])
            g1.markdown(f"**{link.name}** ({link.relation_type.title()})" + (" · primary" if link.is_primary else ""))
            g2.write(link.mobile_number or "-")
            if not link.is_primary and g3.button("Make primary", key=f"stu_primary_{link.link_id}"):
                run_action(guardian_service.set_primary, link.link_id)
                st.rerun()
            if g4.button("Unlink", key=f"stu_unlink_{link.link_id}"):
                run_action(guardian_service.unlink, link.link_id)
                st.rerun()
        if not profile.guardians:
            st.caption("No guardians linked yet.")
        st.markdown("**Link a guardian**")
        link_mode = guardian_mode_selector(f"stu_link_{pid}", allow_skip=False)
        with st.form(f"stu_link_{pid}", clear_on_submit=True):
            picked = guardian_picker(f"stu_link_{pid}", link_mode)
            make_primary = st.checkbox("Primary contact")
            if st.form_submit_button("Link guardian"):
                if not picked or picked.get("missing_name") or picked.get("guardian_id") == -1:
                    st.error("Choose an existing guardian or enter the new guardian's name.")
                else:
                    link_input = run_action(lambda: GuardianLinkInput(**picked, is_primary=make_primary))
                    if link_input and run_action(lambda: guardian_service.link_guardian(pid, link_input) or True):
                        flash("Guardian linked.")
                        st.rerun()

    with t_status:
        if profile.status == StudentStatus.ACTIVE.value:
            with st.form(f"stu_leave_{pid}"):
                st.caption("Monthly fees after the leaving month are removed; paid months are kept.")
                l1, l2 = st.columns(2)
                status = l1.selectbox("New status", [StudentStatus.LEFT.value, StudentStatus.PASSED_OUT.value],
                                      format_func=lambda s: s.replace("_", " ").title())
                leave_date = l2.date_input("Date of leaving", value=today_ist(), max_value=today_ist(),
                                           format="DD/MM/YYYY")
                if st.form_submit_button("Update status"):
                    result = run_action(student_service.mark_left, pid,
                                        StudentLeaving(status=status, date_of_leaving=leave_date))
                    if result is not None:
                        flash(f"Status updated; {result['removed']} future monthly fees removed.")
                        st.rerun()
        else:
            if st.button("Re-activate student", key=f"stu_reactivate_{pid}"):
                run_action(student_service.reactivate, pid)
                flash("Student re-activated. Re-add any fees needed from Collect fees or Admin > Terms & fees.")
                st.rerun()
        if user.is_admin:
            st.markdown("---")
            if profile.has_payments:
                st.caption("This student has payments, so the record cannot be deleted (mark as left instead).")
            else:
                with st.form(f"stu_delete_{pid}"):
                    st.warning("Delete only records created by mistake. This cannot be undone.")
                    confirm = st.text_input(f"Type the admission number {profile.admission_no} to confirm")
                    if st.form_submit_button("Delete student"):
                        if confirm.strip() != profile.admission_no:
                            st.error("The admission number does not match.")
                        elif run_action(lambda: student_service.delete_student(pid) or True):
                            st.session_state.pop(KEY_SELECTED, None)
                            flash(f"Deleted {profile.name}.", "warning")
                            st.rerun()


# ================================================================== tabs
tab_find, tab_add, tab_roll = st.tabs(["Find & manage", "Add student", "Roll numbers"])

# ------------------------------------------------------------------ add
with tab_add:
    st.caption("Choose how the guardian will be added first - the form below adjusts to your choice.")
    add_guardian_mode = guardian_mode_selector("stu_add")
    with st.form("stu_add", clear_on_submit=False):
        st.markdown("##### Student")
        a1, a2, a3 = st.columns(3)
        name = a1.text_input("Full name *")
        dob = a2.date_input("Date of birth", value=None, min_value=today_ist().replace(year=today_ist().year - 25),
                            max_value=today_ist(), format="DD/MM/YYYY")
        category = a3.selectbox("Category *", STUDENT_CATEGORY, index=None)
        b1, b2, b3 = st.columns(3)
        join_date = b1.date_input("Date of joining *", value=today_ist(), max_value=today_ist(), format="DD/MM/YYYY")
        admission_no = b2.text_input("Admission number", placeholder="Leave blank to auto-number")
        notes = b3.text_input("Notes")

        st.markdown("##### Class for the term")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            term = term_select(key="stu_add_term", years=years)
        student_class = c2.selectbox("Class *", CLASSES, index=None)
        section = c3.selectbox("Section *", SECTIONS)
        roll_no = c4.number_input("Roll no (0 = assign later)", min_value=0, value=0, step=1)

        st.markdown("##### Van and Aadhaar")
        v1, v2, v3 = st.columns(3)
        with v1:
            van = rupee_input("Monthly van fee (0 = no van)", key="stu_add_van")
        full_aadhaar = v2.text_input("Aadhaar number (12 digits, stored encrypted)")
        last4 = v3.text_input("...or only last 4 digits", max_chars=4)

        st.markdown(f"##### Guardian ({add_guardian_mode.lower()})")
        guardian = guardian_picker("stu_add", add_guardian_mode)
        submitted = st.form_submit_button("Add student", type="primary")

    if submitted:
        guardian_problem = None
        if guardian and guardian.get("missing_name"):
            guardian_problem = "Enter the guardian's name, or choose 'Skip for now'."
        elif guardian and guardian.get("guardian_id") == -1:
            guardian_problem = "Choose the existing guardian, or select 'New guardian'."

        def build() -> StudentCreate:
            return StudentCreate(
                name=name, date_of_birth=dob, category=category, date_of_join=join_date,
                class_joined=student_class, admission_no=admission_no, notes=notes,
                enrollment={"academic_year_id": term.id, "student_class": student_class,
                            "section": section, "roll_no": roll_no or None},
                van_monthly_paise=van or None,
                identifier={"full_number": full_aadhaar, "last_4_digits": last4}
                if (full_aadhaar.strip() or last4.strip()) else None,
                guardians=[{**guardian, "is_primary": True}] if guardian and not guardian_problem else [],
            )

        data = run_action(build)
        if guardian_problem:
            st.error(guardian_problem)
        elif data:
            created = run_action(student_service.create_student, data)
            if created:
                flash(f"Added {created.name} (admission no {created.admission_no}).")
                st.session_state[KEY_SELECTED] = created.student_id
                st.rerun()

# ------------------------------------------------------------------ find
with tab_find:
    f1, f2, f3, f4, f5, f6 = st.columns([3, 2, 1, 1, 1.4, 1.4])
    text = f1.text_input("Name, admission no, ID or guardian mobile", key="stu_find_text")
    with f2:
        find_term = term_select(key="stu_find_term", years=years)
    with f3:
        find_class = optional_select("Class", CLASSES, key="stu_find_class")
    with f4:
        find_section = optional_select("Section", SECTIONS, key="stu_find_section")
    with f5:
        find_category = optional_select("Category", STUDENT_CATEGORY, key="stu_find_category")
    with f6:
        find_status = optional_select("Status", [s.value for s in StudentStatus], key="stu_find_status")

    results = student_service.search_students(StudentSearch(
        text=text, academic_year_id=find_term.id if find_term else None, student_class=find_class,
        section=find_section, category=find_category, status=find_status))
    st.caption(f"{len(results)} students. Click a row to manage that student.")
    event = st.dataframe(pd.DataFrame([{
        "ID": r.student_id, "Admission no": r.admission_no, "Name": r.name, "Class": f"{r.student_class}-{r.section}",
        "Roll": r.roll_no, "Category": r.category, "Status": r.status, "Guardian": r.guardian_name,
        "Mobile": r.guardian_mobile} for r in results]), hide_index=True, width="stretch",
        on_select="rerun", selection_mode="single-row", key="stu_find_results")
    if event.selection.rows:
        chosen_id = results[event.selection.rows[0]].student_id
        if chosen_id != st.session_state.get(KEY_SELECTED):
            st.session_state[KEY_SELECTED] = chosen_id
            st.rerun()

    selected_id = st.session_state.get(KEY_SELECTED)
    profile: Optional[StudentProfile] = run_action(student_service.get_profile, selected_id) if selected_id else None
    if profile is not None:
        manage_student(profile)

# ------------------------------------------------------------------ roll numbers
with tab_roll:
    o1, o2, o3 = st.columns(3)
    with o1:
        roll_term = term_select(key="stu_roll_term", years=years)
    roll_class = o2.selectbox("Class", CLASSES, key="stu_roll_class")
    roll_section = o3.selectbox("Section", SECTIONS, key="stu_roll_section")
    if roll_term:
        listed = student_service.search_students(StudentSearch(academic_year_id=roll_term.id, student_class=roll_class,
                                                               section=roll_section, status=StudentStatus.ACTIVE.value))
        st.dataframe(pd.DataFrame([{"Roll": r.roll_no, "Name": r.name, "Admission no": r.admission_no}
                                   for r in listed]), hide_index=True, width="stretch")
        b1, b2 = st.columns(2)
        if b1.button("Assign missing roll numbers (alphabetical)"):
            count = run_action(student_service.auto_assign_roll_numbers, roll_term.id, roll_class, roll_section)
            if count is not None:
                flash(f"Assigned {count} roll numbers.")
                st.rerun()
        if user.is_admin and b2.button("Renumber whole section alphabetically"):
            count = run_action(student_service.auto_assign_roll_numbers, roll_term.id, roll_class, roll_section,
                               only_missing=False)
            if count is not None:
                flash(f"Renumbered {count} students.")
                st.rerun()