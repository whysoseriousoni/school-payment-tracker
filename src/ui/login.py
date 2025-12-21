import streamlit as st
from authentication.whoami import get_user_level
from helper.utils import get_or_default


def get_user_details():

    st.markdown("# Login to continue")
    st.text_input(key="USERNAME", label="Username")
    st.text_input(key="PASSWORD", label="Password", type='password')
    username = get_or_default(dictionary=st.session_state, key="USERNAME", default=None)
    password = get_or_default(dictionary=st.session_state, key="PASSWORD", default=None)
    if st.button("Login"):
        if username is not None and password is not None:
            whoami = get_user_level(username, password)
            if whoami != "USER NOT FOUND":
                st.toast("Login successfully")
                st.rerun()
            else:
                st.toast("Invalid username or password")