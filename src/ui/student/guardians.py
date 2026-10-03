import pandas as pd
import streamlit as st

from data_management.dto.guardian import GuardianCreate, GuardianUpdate
from data_management.services import guardian_service
from helper.clock import today_ist
from ui.common import flash, page_header, require_user, run_action

user = require_user()
page_header("Guardians", "One guardian can be linked to several students (siblings). Link them from the Students page.")

search = st.text_input("Search by name or mobile")
guardians = guardian_service.list_guardians(search)
st.dataframe(pd.DataFrame([{"ID": g.id, "Name": g.name, "Mobile": g.mobile_number, "Year of birth": g.year_of_birth,
                            "Students": ", ".join(g.students)} for g in guardians]),
             hide_index=True, width="stretch")

edit_col, add_col = st.columns(2)
with edit_col:
    st.markdown("##### Edit guardian")
    chosen = st.selectbox("Guardian", guardians, index=None, format_func=lambda g: f"{g.name} ({g.mobile_number or '-'})")
    if chosen:
        with st.form(f"guardian_edit_{chosen.id}"):
            name = st.text_input("Name", value=chosen.name)
            mobile = st.text_input("Mobile", value=chosen.mobile_number or "")
            yob = st.number_input("Year of birth (0 = unknown)", min_value=0, max_value=today_ist().year,
                                  value=chosen.year_of_birth or 0)
            if st.form_submit_button("Save", type="primary"):
                data = run_action(lambda: GuardianUpdate(name=name, mobile_number=mobile, year_of_birth=yob or None))
                if data and run_action(lambda: guardian_service.update_guardian(chosen.id, data) or True):
                    flash("Guardian saved.")
                    st.rerun()
        if not chosen.students and st.button("Delete this guardian (not linked to any student)"):
            if run_action(lambda: guardian_service.delete_guardian(chosen.id) or True):
                flash("Guardian deleted.", "warning")
                st.rerun()

with add_col:
    st.markdown("##### Add guardian")
    with st.form("guardian_add", clear_on_submit=True):
        name = st.text_input("Name")
        mobile = st.text_input("Mobile")
        yob = st.number_input("Year of birth (0 = unknown)", min_value=0, max_value=today_ist().year, value=0)
        if st.form_submit_button("Add guardian"):
            data = run_action(lambda: GuardianCreate(name=name, mobile_number=mobile, year_of_birth=yob or None))
            if data and run_action(guardian_service.create_guardian, data):
                flash(f"Added guardian {data.name}.")
                st.rerun()
