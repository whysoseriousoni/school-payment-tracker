import streamlit as st

def get_user_level(username, password):
    if username=="ADMIN" and password=="School@dmin":
        st.session_state["USER_TYPE"] = "ADMIN"
        return "ADMIN"
    elif username=="BILLING" and password=="SchoolBiller":
        st.session_state["USER_TYPE"] = "BILLER"
        return "BILLER"
    st.session_state["USER_TYPE"] = "NONE"
    return "USER NOT FOUND"