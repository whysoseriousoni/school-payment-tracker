import streamlit as st

from helper.utils import get_or_default
from ui.login import get_user_details
st.markdown("# School Billing Payment System")

is_authenticated = get_or_default(dictionary=st.session_state, key="LOGGED_IN", default=False)
is_admin = get_or_default(dictionary=st.session_state, key="ADMIN_FLAG", default=False)
whoami = get_or_default(dictionary=st.session_state, key="USER_TYPE", default=False)

if not is_authenticated:
    get_user_details()
    st.stop()