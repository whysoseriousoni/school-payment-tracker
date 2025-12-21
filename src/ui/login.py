import streamlit as st
from authentication.whoami import get_user_level
from helper.utils import get_or_default


def get_user_details():

    st.markdown("# Login to continue")
    st.text_input(key="USERNAME", label="Username")
    st.text_input(key="PASSWORD", label="Password", type='password')
    username = get_or_default(dictionary=st.session_state, key="USERNAME", default=None)
    password = get_or_default(dictionary=st.session_state, key="PASSWORD", default=None)
    if username is not None and password is not None:
        get_user_level(username, password)
    