import pandas as pd
import streamlit as st

from data_management.dto.academic_year import AcademicYearCreate
from data_management.dto.fee import FeeStructureInput
from data_management.services import academic_year_service, fee_service, settings_service
from helper.money import rupees_to_paise
from statics import CLASSES, FeeType
from ui.common import flash, page_header, require_user, run_action, term_select

user = require_user(admin_only=True)
page_header("Terms & fees")
tab_terms, tab_fees, tab_school = st.tabs(["Academic terms", "Fee structure", "School details"])

with tab_terms:
    years = academic_year_service.list_years()
    st.dataframe(pd.DataFrame([{"Term": y.label, "Starts": y.start_date, "Ends": y.end_date,
                                "Current": "Yes" if y.is_current else ""} for y in years]),
                 hide_index=True, width="stretch")
    c1, c2 = st.columns(2)
    with c1, st.form("setup_new_term"):
        latest = max((y.start_date.year for y in years), default=2025)
        start_year = st.number_input("New term starting June of", min_value=2000, max_value=2100, value=latest + 1)
        make_current = st.checkbox("Make it the current term")
        if st.form_submit_button("Create term"):
            created = run_action(academic_year_service.create_year,
                                 AcademicYearCreate(start_year=int(start_year), make_current=make_current))
            if created:
                flash(f"Created term {created.label}. Set its fee structure next.")
                st.rerun()
    with c2, st.form("setup_current_term"):
        chosen = st.selectbox("Current term", years, format_func=lambda y: y.label,
                              index=next((i for i, y in enumerate(years) if y.is_current), 0))
        if st.form_submit_button("Set as current"):
            if run_action(lambda: academic_year_service.set_current_year(chosen.id) or True):
                flash(f"{chosen.label} is now the current term.")
                st.rerun()

with tab_fees:
    term = term_select(key="setup_fee_term")
    if term:
        existing = {(s.student_class, s.fee_type): s.monthly_amount_paise for s in fee_service.list_structures(term.id)}
        table = pd.DataFrame({
            "Class": CLASSES,
            "Tuition per month (₹)": [existing.get((c, FeeType.TUITION.value), 0) / 100 for c in CLASSES],
            "Default van per month (₹)": [existing.get((c, FeeType.VAN.value), 0) / 100 for c in CLASSES],
        })
        table["Tuition per year (₹)"] = table["Tuition per month (₹)"] * 12
        st.caption("Tuition is charged monthly from June to May. The van amount is only the default offered when a "
                   "student opts in.")
        edited = st.data_editor(table, hide_index=True, width="stretch", key=f"setup_fee_editor_{term.id}",
                                disabled=["Class", "Tuition per year (₹)"],
                                column_config={c: st.column_config.NumberColumn(min_value=0.0, step=50.0, format="%.2f")
                                               for c in ("Tuition per month (₹)", "Default van per month (₹)")})
        if st.button("Save fee structure", type="primary"):
            saved = 0
            for row in edited.to_dict("records"):
                for column, fee_type in (("Tuition per month (₹)", FeeType.TUITION.value),
                                         ("Default van per month (₹)", FeeType.VAN.value)):
                    amount = rupees_to_paise(row[column] or 0)
                    if amount or (row["Class"], fee_type) in existing:
                        if run_action(fee_service.save_structure, FeeStructureInput(
                                academic_year_id=term.id, student_class=row["Class"], fee_type=fee_type,
                                monthly_amount_paise=amount)) is None:
                            st.stop()
                        saved += 1
            flash(f"Saved {saved} fee amounts for {term.label}. Apply them to students below.")
            st.rerun()

        st.markdown("##### Apply tuition to enrolled students")
        st.caption("Creates any missing monthly tuition fees (from each student's joining month). New students get "
                   "fees automatically; use this after setting or changing the structure.")
        update_unpaid = st.checkbox("Also change the amount of months that have no payment yet")
        if st.button("Apply to students"):
            result = run_action(fee_service.apply_tuition_structure, term.id, None, update_unpaid)
            if result:
                flash(f"Created {result['created']} monthly fees, updated {result['updated']}.")
                st.rerun()

with tab_school:
    values = settings_service.get_settings()
    with st.form("setup_school"):
        name = st.text_input("School name", value=values[settings_service.SCHOOL_NAME])
        address = st.text_area("Address", value=values[settings_service.SCHOOL_ADDRESS])
        phone = st.text_input("Phone", value=values[settings_service.SCHOOL_PHONE])
        if st.form_submit_button("Save", type="primary"):
            if run_action(lambda: settings_service.save_settings({
                    settings_service.SCHOOL_NAME: name, settings_service.SCHOOL_ADDRESS: address,
                    settings_service.SCHOOL_PHONE: phone}) or True):
                flash("School details saved; they appear on receipts and reports.")
                st.rerun()
