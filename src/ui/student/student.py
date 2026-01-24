from datetime import datetime, timedelta
import time as _time
from num2words import num2words
import pandas as pd
from sqlmodel import Session, create_engine
import streamlit as st

from alterlit.alternatives import date_input
from data_management.BillingDetail import BillingDetail
from data_management.StudentBill import get_all_bills
from helper.utils import get_index_or_default, get_or_default
from ui.login import get_user_details
import st_pydantic as sp
from data_management.Student import Student, get_students

st.markdown("# About Student Section")

is_authenticated = get_or_default(
    dictionary=st.session_state, key="LOGGED_IN", default=False
)
is_admin = get_or_default(dictionary=st.session_state, key="ADMIN_FLAG", default=False)
whoami = get_or_default(dictionary=st.session_state, key="USER_TYPE", default=False)

# if not is_authenticated:
#     get_user_details()
#     st.stop()

## ----- STUDENT SELECTION ----- ##
CURRENT_CLASS_OPTIONS = [
    "UKG",
    "LKG",
    "CLASS 1",
    "CLASS 2",
    "CLASS 3",
    "CLASS 4",
    "CLASS 5",
    "CLASS 6",
    "CLASS 7",
    "CLASS 8",
    "CLASS 9",
    "CLASS 10",
]

st.markdown(body="## Add New Student Information")

with st.expander(label="### Add New Student Information", expanded=True):
    student_name = st.text_input(
        key="NEW_STUDENT_NAME",
        label="Student Name",
    )
    date_of_birth = date_input(
        key="NEW_STUDENT_DATE_OF_BIRTH",
        label="Date Of Birth",
        default_value=None,
        max_value=datetime.now(),
    )
    new_student_current_class = get_or_default(
        dictionary=st.session_state, key="NEW_STUDENT_CURRENT_CLASS", default=None
    )
    st.selectbox(
        options=CURRENT_CLASS_OPTIONS,
        key="NEW_STUDENT_CURRENT_CLASS",
        label="Current Class",
        index=get_index_or_default(
            options=CURRENT_CLASS_OPTIONS,
            search_for=new_student_current_class,
            default=0,
        ),
    )

    date_of_joining = date_input(
        key="NEW_STUDENT_DATE_OF_JOINING",
        label="Date Of Joining",
        default_value=None,
        max_value=datetime.now(),
    )
    date_of_relieve = date_input(
        key="NEW_STUDENT_DATE_OF_RELIEVE",
        label="Date Of Relieve",
        default_value=None,
        max_value=datetime.now(),
    )

    lkg_date_of_join = date_input(
        key="NEW_STUDENT_LKG_JOINING_DATE",
        label="LKG Joining Date",
        default_value=None,
        max_value=datetime.now(),
    )
    ukg_date_of_join = date_input(
        key="NEW_STUDENT_UKG_JOINING_DATE",
        label="UKG Joining Date",
        default_value=None,
        max_value=datetime.now(),
    )
    class_1_date_of_join = date_input(
        key="NEW_STUDENT_CLASS_1_JOINING_DATE",
        label="CLASS 1 Joining Date",
        default_value=None,
        max_value=datetime.now(),
    )
    class_2_date_of_join = date_input(
        key="NEW_STUDENT_CLASS_2_JOINING_DATE",
        label="CLASS 2 Joining Date",
        default_value=None,
        max_value=datetime.now(),
    )
    class_3_date_of_join = date_input(
        key="NEW_STUDENT_CLASS_3_JOINING_DATE",
        label="CLASS 3 Joining Date",
        default_value=None,
        max_value=datetime.now(),
    )
    class_4_date_of_join = date_input(
        key="NEW_STUDENT_CLASS_4_JOINING_DATE",
        label="CLASS 4 Joining Date",
        default_value=None,
        max_value=datetime.now(),
    )
    class_5_date_of_join = date_input(
        key="NEW_STUDENT_CLASS_5_JOINING_DATE",
        label="CLASS 5 Joining Date",
        default_value=None,
        max_value=datetime.now(),
    )
    class_6_date_of_join = date_input(
        key="NEW_STUDENT_CLASS_6_JOINING_DATE",
        label="CLASS 6 Joining Date",
        default_value=None,
        max_value=datetime.now(),
    )
    class_7_date_of_join = date_input(
        key="NEW_STUDENT_CLASS_7_JOINING_DATE",
        label="CLASS 7 Joining Date",
        default_value=None,
        max_value=datetime.now(),
    )
    class_8_date_of_join = date_input(
        key="NEW_STUDENT_CLASS_8_JOINING_DATE",
        label="CLASS 8 Joining Date",
        default_value=None,
        max_value=datetime.now(),
    )
    class_9_date_of_join = date_input(
        key="NEW_STUDENT_CLASS_9_JOINING_DATE",
        label="CLASS 9 Joining Date",
        default_value=None,
        max_value=datetime.now(),
    )
    class_10_date_of_join = date_input(
        key="NEW_STUDENT_CLASS_10_JOINING_DATE",
        label="CLASS 10 Joining Date",
        default_value=None,
        max_value=datetime.now(),
    )
    if st.button("Add New Student"):
        st.toast("Adding New Student ...")

        new_student_detail = Student(
            student_name=get_or_default(
                dictionary=st.session_state, key="NEW_STUDENT_NAME", default=None
            ),
            date_of_birth=get_or_default(
                dictionary=st.session_state,
                key="NEW_STUDENT_DATE_OF_BIRTH",
                default=None,
            ),
            current_class=get_or_default(
                dictionary=st.session_state,
                key="NEW_STUDENT_CURRENT_CLASS",
                default=None,
            ),
            date_of_joining=get_or_default(
                dictionary=st.session_state,
                key="NEW_STUDENT_DATE_OF_JOINING",
                default=None,
            ),
            date_of_relieve=get_or_default(
                dictionary=st.session_state,
                key="NEW_STUDENT_DATE_OF_RELIEVE",
                default=None,
            ),
            lkg_date_of_join=get_or_default(
                dictionary=st.session_state,
                key="NEW_STUDENT_LKG_JOINING_DATE",
                default=None,
            ),
            ukg_date_of_join=get_or_default(
                dictionary=st.session_state,
                key="NEW_STUDENT_UKG_JOINING_DATE",
                default=None,
            ),
            class_1_date_of_join=get_or_default(
                dictionary=st.session_state,
                key="NEW_STUDENT_CLASS_1_JOINING_DATE",
                default=None,
            ),
            class_2_date_of_join=get_or_default(
                dictionary=st.session_state,
                key="NEW_STUDENT_CLASS_2_JOINING_DATE",
                default=None,
            ),
            class_3_date_of_join=get_or_default(
                dictionary=st.session_state,
                key="NEW_STUDENT_CLASS_3_JOINING_DATE",
                default=None,
            ),
            class_4_date_of_join=get_or_default(
                dictionary=st.session_state,
                key="NEW_STUDENT_CLASS_4_JOINING_DATE",
                default=None,
            ),
            class_5_date_of_join=get_or_default(
                dictionary=st.session_state,
                key="NEW_STUDENT_CLASS_5_JOINING_DATE",
                default=None,
            ),
            class_6_date_of_join=get_or_default(
                dictionary=st.session_state,
                key="NEW_STUDENT_CLASS_6_JOINING_DATE",
                default=None,
            ),
            class_7_date_of_join=get_or_default(
                dictionary=st.session_state,
                key="NEW_STUDENT_CLASS_7_JOINING_DATE",
                default=None,
            ),
            class_8_date_of_join=get_or_default(
                dictionary=st.session_state,
                key="NEW_STUDENT_CLASS_8_JOINING_DATE",
                default=None,
            ),
            class_9_date_of_join=get_or_default(
                dictionary=st.session_state,
                key="NEW_STUDENT_CLASS_9_JOINING_DATE",
                default=None,
            ),
            class_10_date_of_join=get_or_default(
                dictionary=st.session_state,
                key="NEW_STUDENT_CLASS_10_JOINING_DATE",
                default=None,
            ),
        )
        engine = create_engine("sqlite:///data_store/database.db")
        with Session(engine) as session:
            try:
                session.add(new_student_detail)
                session.commit()
                st.toast("Successfully added new Student")
                st.toast("Resetting page")
                _time.sleep(3)
                st.rerun()
            except Exception as ex:
                st.error(f"Error in adding new student {ex}")
                print(ex)


st.divider()

st.markdown("## All Student Information")

st.dataframe(data=get_students())