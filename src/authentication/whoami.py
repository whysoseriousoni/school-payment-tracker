import streamlit as st

def get_user_level(username, password):
    if str(username).upper()=="ADMIN" and password=="School@dmin":
        st.session_state["LOGGED_IN"] = True
        st.session_state["ADMIN_FLAG"] = True
        st.session_state["USER_TYPE"] = "ADMIN"
        return "ADMIN"
    elif str(username).upper()=="BILLING" and password=="SchoolBiller":
        st.session_state["LOGGED_IN"] = True
        st.session_state["ADMIN_FLAG"] = True
        st.session_state["USER_TYPE"] = "BILLER"
        return "BILLER"
    st.session_state["USER_TYPE"] = "NONE"
    st.session_state["LOGGED_IN"] = False
    st.session_state["ADMIN_FLAG"] = False
    st.session_state["USER_TYPE"] = "NONE"
    return "USER NOT FOUND"