import streamlit as st

from data_management.dto.user import UserCreate
from data_management.services import auth_service
from statics import UserRole
from ui.common import SESSION_USER, run_action


def _first_admin_setup() -> None:
    st.title("Welcome - first-time setup")
    st.write("Create the administrator account. You can add billing staff afterwards from Admin > Users.")
    with st.form("first_admin"):
        username = st.text_input("Administrator username", value="admin")
        password = st.text_input("Password (8+ characters, letters and numbers)", type="password")
        confirm = st.text_input("Confirm password", type="password")
        submitted = st.form_submit_button("Create administrator", type="primary")
    if submitted:
        if password != confirm:
            st.error("The passwords do not match.")
            return
        user = run_action(lambda: auth_service.create_first_admin(
            UserCreate(username=username, password=password, role=UserRole.ADMIN.value)))
        if user:
            st.session_state[SESSION_USER] = user
            st.rerun()


def login_page() -> None:
    if auth_service.needs_first_admin():
        _first_admin_setup()
        return
    st.title("School Fee Tracker")
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in", type="primary")
    if submitted:
        user = auth_service.authenticate(username, password)
        if user is None:
            st.error("Invalid username or password.")
        else:
            st.session_state[SESSION_USER] = user
            st.rerun()
