from datetime import datetime, timedelta
from num2words import num2words
from sqlmodel import Session, create_engine
import streamlit as st
import time as _time

from alterlit.alternatives import date_input
from data_management.BillingDetail import BillingDetail
from data_management.sql_manager import get_engine
from helper.utils import get_index_or_default, get_or_default
from ui.login import get_user_details

st.markdown("# Billing Section")

is_authenticated = get_or_default(
    dictionary=st.session_state, key="LOGGED_IN", default=False
)
is_admin = get_or_default(dictionary=st.session_state, key="ADMIN_FLAG", default=False)
whoami = get_or_default(dictionary=st.session_state, key="USER_TYPE", default=False)

# if not is_authenticated:
#     get_user_details()
#     st.stop()

## ----- STUDENT SELECTION ----- ##

st.markdown("### Select Student Information")
st.text_input(label="Enter Student ID", key="STUDENT_ID")
st.text_input(label="Enter Student Name", key="STUDENT_NAME")

st.divider()

## ----- BILLING SELECTION ----- ##

BILLING_TYPES = [
    "Term Fee",
    "Van Fee",
    "Uniform Fee",
    "Book Fee",
    "Petrol Fee",
    # Excluded as per requirement
    # "Computer Fee",
    # "Exam Fee",
    # "ID Fee",
    # "Lunch Fee",
]

#
billing_date = date_input(
    key="BILLING_DATE", label="Billing Date", max_value=datetime.now()
)


# "Custom Fee",

billing_type = get_or_default(
    dictionary=st.session_state, key="BILLING_TYPE", default=None
)
CUSTOM_BILLING_TYPE = "Custom Fee"

st.selectbox(
    options=[*BILLING_TYPES, CUSTOM_BILLING_TYPE],
    key="BILLING_TYPE",
    label="Choose Billing Type",
    index=get_index_or_default(
        options=BILLING_TYPES, search_for=billing_type, default=0
    ),
)

if billing_type == CUSTOM_BILLING_TYPE:
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


if st.button(label="Create Bill"):
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
