import pandas as pd
import streamlit as st

from data_management.dto.academic_year import AcademicYearCreate
from data_management.services import academic_year_service, settings_service
from ui.common import flash, page_header, require_user, run_action

user = require_user(admin_only=True)
page_header("Terms & school", "Fees are set per term in Admin > Fee plans.")
tab_terms, tab_school = st.tabs(["Academic terms", "School details"])

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
                flash(f"Created term {created.label}. Set up its fee plans next (Admin > Fee plans > Copy).")
                st.rerun()
    with c2, st.form("setup_current_term"):
        chosen = st.selectbox("Current term", years, format_func=lambda y: y.label,
                              index=next((i for i, y in enumerate(years) if y.is_current), 0))
        if st.form_submit_button("Set as current"):
            if run_action(lambda: academic_year_service.set_current_year(chosen.id) or True):
                flash(f"{chosen.label} is now the current term.")
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
