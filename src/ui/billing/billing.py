from datetime import datetime, timedelta
from num2words import num2words
from sqlmodel import Session, create_engine
import streamlit as st

from alterlit.alternatives import date_input
from data_management.BillingDetail import BillingDetail
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

st.text_input(label="Billing Amount in Words (₹)", value=f"₹ {num2words(billing_amount)}", disabled=True)

if st.button(label="Create Bill"):
    st.toast("Initiating Bill Creation")
    billing_detail = BillingDetail(
        student_id=get_or_default(dictionary=st.session_state, key="", default=None),
        student_name=get_or_default(dictionary=st.session_state, key="", default=None),
        bill_date=get_or_default(dictionary=st.session_state, key="", default=None),
        bill_type=get_or_default(dictionary=st.session_state, key="", default=None),
        bill_amount=get_or_default(dictionary=st.session_state, key="BILLING_AMOUNT", default=None),
        billing_amount_in_words=get_or_default(dictionary=st.session_state, key="", default=None),
    )
    engine = create_engine("sqlite:///data_store/database.db")
    with Session(engine) as session:
        session.add(billing_detail)
    
    
    
