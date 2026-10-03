import streamlit as st

from data_management.dto.user import PasswordChange
from data_management.services import auth_service
from ui.common import flash, page_header, require_user, run_action

user = require_user()
page_header("My account", f"Signed in as {user.username} ({user.role.title()})")

with st.form("change_password", clear_on_submit=True):
    current = st.text_input("Current password", type="password")
    new = st.text_input("New password", type="password")
    confirm = st.text_input("Confirm new password", type="password")
    submitted = st.form_submit_button("Change password", type="primary")

if submitted:
    if auth_service.authenticate(user.username, current) is None:
        st.error("The current password is not correct.")
    elif new != confirm:
        st.error("The new passwords do not match.")
    else:
        changed = run_action(lambda: auth_service.change_password(
            PasswordChange(user_id=user.id, new_password=new)) or True)
        if changed:
            flash("Password changed.")
            st.rerun()
