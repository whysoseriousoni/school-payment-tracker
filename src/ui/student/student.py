from datetime import datetime, timedelta
import time as _time
from num2words import num2words
import pandas as pd
from sqlmodel import Session, create_engine
import streamlit as st
from statics import CLASSES, USER_IDENTIFIER_TYPES, STUDENT_CATEGORY
from alterlit.alternatives import date_input
from data_management.dao.BillingDetail import BillingDetail
from data_management.StudentBill import get_all_bills, get_students
from data_management.sql_manager import get_engine
from helper.utils import get_index_or_default, get_or_default
from ui.login import get_user_details
import st_pydantic as sp
from data_management.dao.Student import Student

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

st.markdown(body="## Add New Student Information")

with st.expander(label="Add New Student Information", expanded=True):
    student_name = st.text_input(
        key="NEW_STUDENT_NAME",
        label="Student Name _(Required)_",
    )

    date_of_birth = date_input(
        key="NEW_STUDENT_DATE_OF_BIRTH",
        label="Date Of Birth _(Required)_",
        default_value=None,
        max_value=datetime.now(),
    )

    new_student_class_joined = get_or_default(
        dictionary=st.session_state, key="NEW_STUDENT_CLASS_JOINED", default=None
    )
    st.selectbox(
        options=CLASSES,
        key="NEW_STUDENT_CLASS_JOINED",
        label="Class Joined _(Required)_",
        index=get_index_or_default(
            options=CLASSES,
            search_for=new_student_class_joined,
            default=0,
        ),
    )

    date_of_joining = date_input(
        key="NEW_STUDENT_DATE_OF_JOINING",
        label="Date Of Joining _(Required)_",
        default_value=None,
        max_value=datetime.now(),
    )
    
    new_student_current_class = get_or_default(
        dictionary=st.session_state, key="NEW_STUDENT_CURRENT_CLASS", default=None
    )
    st.selectbox(
        options=CLASSES,
        key="NEW_STUDENT_CURRENT_CLASS",
        label="Current Class _(Required)_",
        index=get_index_or_default(
            options=CLASSES,
            search_for=new_student_current_class,
            default=0,
        ),
    )

    new_student_category = get_or_default(
        dictionary=st.session_state, key="NEW_STUDENT_CATEGORY", default=None
    )
    st.selectbox(
        options=STUDENT_CATEGORY,
        key="NEW_STUDENT_CATEGORY",
        label="Category _(Required)_",
        index=get_index_or_default(
            options=STUDENT_CATEGORY,
            search_for=new_student_category,
            default=0,
        ),
    )
    
    
    st.selectbox(
        options=USER_IDENTIFIER_TYPES,
        key="NEW_STUDENT_IDENTIFIER_TYPE",
        label="Identifier Type _(Required)_",
        index=get_index_or_default(
            options=USER_IDENTIFIER_TYPES,
            search_for="AADHAR",
            default=0,
        ),
        disabled=True
    )
    
    last_4_digit_of_identifier = st.text_input(
        key="NEW_STUDENT_LAST_4_DIGIT_OF_IDENTIFIER",
        label="Last 4 Digit of Identifier", max_chars=4, 
    )

    if st.button("Add New Student"):
        st.toast("Adding New Student ...")
        new_student_detail = None
        try:
            st.toast("Trying to create new student record")
            new_student_detail = Student(
                name=get_or_default(
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
                date_of_join=get_or_default(
                    dictionary=st.session_state,
                    key="NEW_STUDENT_DATE_OF_JOINING",
                    default=None,
                ),
                identifier_type=get_or_default(
                    dictionary=st.session_state,
                    key="NEW_STUDENT_IDENTIFIER_TYPE",
                    default="AADHAR",
                ),
                last_4_digit_of_identifier=get_or_default(
                    dictionary=st.session_state,
                    key="NEW_STUDENT_LAST_4_DIGIT_OF_IDENTIFIER",
                    default=None,
                ),
                category=get_or_default(
                    dictionary=st.session_state,
                    key="NEW_STUDENT_CATEGORY",
                    default=None,
                ),
                
            )
        except Exception as ex:
            st.error("Unable to create new student record")
            st.error("Populate required fields")
            st.toast("Unable to create new student record")
            st.stop()

        engine = get_engine()
        with Session(engine) as session:
            try:
                session.add(new_student_detail)
                session.commit()
                st.toast("Successfully added new Student")
                st.toast("Resetting page")
                _time.sleep(3)
                st.rerun(scope="app")
            except Exception as ex:
                st.error(f"Error in adding new student to database. Exception: {ex}")
                print(ex)


st.divider()

st.markdown("## All Student Information")

st.dataframe(data=get_students())