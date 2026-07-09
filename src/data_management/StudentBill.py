from typing import Optional
import pandas as pd
from sqlmodel import Field, Relationship, SQLModel, Session, create_engine, join, select
from datetime import datetime
from data_management.dao.GuardianDetails import GuardianDetails
from data_management.dao.Student import Student
from data_management.dao.BillingDetail import BillingDetail
from data_management.sql_manager import get_engine
from helper.utils import model_dump_with_prefix_alias, sqlmodel_to_df
import streamlit as st


def get_all_bills(student_id:int):
    # TODO: Incomplete function
    with Session(get_engine()) as session:
        # Student
        student_sql_statement = select(Student).where(Student.student_id==student_id)
        student = session.exec(student_sql_statement).first()
        print(student)
        
        # Bills
        bill_sql_statement = select(BillingDetail).where(BillingDetail.student_id==student_id).order_by(BillingDetail.bill_date)
        bills = session.exec(bill_sql_statement).fetchall()
        print(bills)
        

@st.cache_data(ttl=10)
def get_students(student_id: int = None):
    students = []
    try:
        engine = get_engine()
        with Session(engine) as session:
            # Student
            student_sql_statement = select(Student)
            if student_id:
                student_sql_statement = student_sql_statement.where(Student.id == student_id)
            students = session.exec(student_sql_statement).fetchall()
            return sqlmodel_to_df(students)
    except Exception as ex:
        return sqlmodel_to_df(students)

def get_guardians(guardian_id: int = None):
    engine = get_engine()

    with Session(engine) as session:
        # Student
        guardian_sql_statement = select(GuardianDetails)
        guardians = []
        if guardian_id:
            guardian_sql_statement = guardian_sql_statement.where(GuardianDetails.id == guardian_id)
        guardians = session.exec(guardian_sql_statement).fetchall()
        return sqlmodel_to_df(guardians)

def get_complete_student_detail(student_id: int, guardian_count=1):
    student = {}
    try:
        engine = get_engine()
        with Session(engine) as session:
            # Student
            student_sql_statement = select(Student, GuardianDetails).join(target=GuardianDetails, onclause=Student.id==GuardianDetails.student_id)
            student_sql_statement = student_sql_statement.where(Student.id == student_id).limit(1)
            student_search_result = session.exec(student_sql_statement).fetchall()
            if len(student_search_result)>0:
                # Filter for 1
                for _student_, _guardian_ in student_search_result:
                    student.update(model_dump_with_prefix_alias(_student_.model_dump(), "student"))
                    student.update(model_dump_with_prefix_alias(_guardian_.model_dump(), "guardian"))
                
            # Guardian
            

            return student
    except Exception as ex:
        return student