from datetime import datetime, timedelta
from num2words import num2words
from sqlmodel import Session, create_engine
from data_management.StudentBill import get_complete_student_detail, get_students
from statics import BILLING_TYPES
import streamlit as st
import time as _time

from alterlit.alternatives import date_input
from data_management.dao.BillingDetail import BillingDetail
from data_management.sql_manager import get_engine
from helper.utils import get_index_or_default, get_or_default
from ui.login import get_user_details

st.markdown("# Billing Section")

# is_authenticated = get_or_default(
#     dictionary=st.session_state, key="LOGGED_IN", default=False
# )
# is_admin = get_or_default(dictionary=st.session_state, key="ADMIN_FLAG", default=False)
# whoami = get_or_default(dictionary=st.session_state, key="USER_TYPE", default=False)

# if not is_authenticated:
#     get_user_details()
#     st.stop()

## ----- STUDENT SELECTION ----- ##
with st.expander(label="Select Student For Billing", expanded=True):
    st.markdown("### Search For Student Information")
    st.text_input(label="Enter Student ID", key="STUDENT_ID")
    # st.text_input(label="Enter Student Name", key="STUDENT_NAME")
    if st.button(label="Search Using Student ID",):
        selected_student_id = get_or_default(dictionary=st.session_state, key="STUDENT_ID", default=None)
        if selected_student_id is None:
            st.toast("Enter Student ID or Student Name")
            st.stop()
        student_data = get_complete_student_detail(student_id=selected_student_id)
        st.session_state["SELECTED_STUDENT_DATA"] = student_data
        st.toast("Found Student... Refreshing contents")
        st.rerun()
st.divider()


# Form


## ----- BILLING SELECTION ----- ##

student_detail_section_column, billing_section_column = st.columns([0.5, 0.5])

with student_detail_section_column:
    selected_student_details = st.session_state.get("SELECTED_STUDENT_DATA", None)
    if selected_student_details is None:
        selected_student_name = ""
        selected_student_dob = ""
        selected_student_category = ""
        selected_student_current_class = ""
        selected_student_date_of_join = ""
        selected_student_aadhar_4_digit = ""
        selected_student_guardian_name = ""
        selected_student_guardian_relation = ""
        selected_student_guardian_phone_number = ""
    else:
        selected_student_name = selected_student_details.get("student_name")
        selected_student_dob = selected_student_details.get("student_date_of_birth")
        selected_student_category = selected_student_details.get("student_category")
        selected_student_current_class = selected_student_details.get("student_current_class")
        selected_student_date_of_join = selected_student_details.get("student_date_of_join")
        selected_student_aadhar_4_digit = selected_student_details.get("student_last_4_digit_of_identifier")
        selected_student_guardian_name = selected_student_details.get("guardian_name")
        selected_student_guardian_relation = selected_student_details.get("guardian_relation_type")
        selected_student_guardian_phone_number = selected_student_details.get("guardian_mobile_number")

    
    st.text_input(label="Student Name", value=selected_student_name, disabled=True)
    st.text_input(label="Date Of Birth", value=selected_student_dob, disabled=True)
    st.text_input(label="Category", value=selected_student_category, disabled=True)
    st.text_input(label="Current Class", value=selected_student_current_class, disabled=True)
    st.text_input(label="Date Of Join", value=selected_student_date_of_join, disabled=True)
    st.text_input(label="AADHAR Last 4 Digits", value=selected_student_aadhar_4_digit, disabled=True)
    st.text_input(label="Guardian Name", value=selected_student_guardian_name, disabled=True)
    st.text_input(label="Guardian Relation", value=selected_student_guardian_relation, disabled=True)
    st.text_input(label="Guardian Phone Number", value=selected_student_guardian_phone_number, disabled=True)
    

with billing_section_column:
    #
    billing_date = date_input(
        key="BILLING_DATE", label="Billing Date", max_value=datetime.now()
    )


    # "Custom Fee",

    billing_type = get_or_default(
        dictionary=st.session_state, key="BILLING_TYPE", default=None
    )

    st.selectbox(
        options=BILLING_TYPES,
        key="BILLING_TYPE",
        label="Choose Billing Type",
        index=get_index_or_default(
            options=BILLING_TYPES, search_for=billing_type, default=0
        ),
    )

    if billing_type == BILLING_TYPES[-1]:
        # Overwrite
        st.text_input(label="Enter Billing Type", key="CUSTOM_BILL_TYPE")
        billing_type = get_or_default(
            dictionary=st.session_state, key="CUSTOM_BILL_TYPE", default=""
        )

    billing_amount = st.number_input(
        label="Bill Amount (₹)",
        icon="💵",
        min_value=0.0,
        help="Enter Amount (INR)",
        key="BILLING_AMOUNT",
        format="%.2f",
    )

    billing_amount_in_words = num2words(
        get_or_default(st.session_state, "BILLING_AMOUNT", default=0)
    )
    st.text_input(
        label="Billing Amount in Words (₹)",
        value=f"₹ {billing_amount_in_words}",
        disabled=True,
    )


if st.button(label="Create Bill", use_container_width=True):
    st.toast("Initiating Bill Creation")
    billing_detail = BillingDetail(
        student_id=int(
            get_or_default(dictionary=st.session_state, key="STUDENT_ID", default=None)
        ),
        student_name=get_or_default(
            dictionary=st.session_state, key="STUDENT_NAME", default=None
        ),
        bill_date=get_or_default(
            dictionary=st.session_state, key="BILLING_DATE", default=None
        ),
        bill_type=get_or_default(
            dictionary=st.session_state, key="BILLING_TYPE", default=None
        ),
        bill_amount=get_or_default(
            dictionary=st.session_state, key="BILLING_AMOUNT", default=None
        ),
        billing_amount_in_words=billing_amount_in_words,
    )
    
    with Session(get_engine()) as session:
        try:
            session.add(billing_detail)
            session.commit()
            st.toast("Bill saved successfully")
            _time.sleep(3)
            st.rerun()
        except Exception as ex:
            print(f"Error during writing to BillingDetail table | {ex}")
