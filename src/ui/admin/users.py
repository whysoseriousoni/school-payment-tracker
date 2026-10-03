import pandas as pd
import streamlit as st

from data_management.dto.user import PasswordChange, UserCreate
from data_management.services import auth_service
from statics import UserRole
from ui.common import flash, page_header, require_user, run_action

user = require_user(admin_only=True)
page_header("Users", "Administrators can do everything; billers can manage students and collect fees, "
                     "but cannot void receipts or open Admin pages.")

users = auth_service.list_users()
st.dataframe(pd.DataFrame([{"Username": u.username, "Role": u.role.title(), "Active": "Yes" if u.is_active else "No",
                            "Last login": u.last_login_on} for u in users]), hide_index=True, width="stretch")

left, right = st.columns(2)
with left, st.form("users_add", clear_on_submit=True):
    st.markdown("##### Add user")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    role = st.selectbox("Role", [r.value for r in UserRole], index=1, format_func=str.title)
    if st.form_submit_button("Add user", type="primary"):
        created = run_action(lambda: auth_service.create_user(UserCreate(username=username, password=password, role=role)))
        if created:
            flash(f"User {created.username} added.")
            st.rerun()

with right:
    st.markdown("##### Manage user")
    chosen = st.selectbox("User", users, format_func=lambda u: f"{u.username} ({u.role.title()})")
    with st.form(f"users_reset_{chosen.id}", clear_on_submit=True):
        new_password = st.text_input("New password", type="password")
        if st.form_submit_button("Reset password"):
            if run_action(lambda: auth_service.change_password(
                    PasswordChange(user_id=chosen.id, new_password=new_password)) or True):
                flash(f"Password reset for {chosen.username}.")
                st.rerun()
    label = "Deactivate" if chosen.is_active else "Activate"
    if st.button(f"{label} {chosen.username}"):
        if run_action(lambda: auth_service.set_active(chosen.id, not chosen.is_active, user.id) or True):
            flash(f"{chosen.username} {label.lower()}d.")
            st.rerun()
