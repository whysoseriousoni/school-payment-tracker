from typing import Optional
from sqlmodel import Field, Relationship, SQLModel, Session, create_engine, select
from datetime import datetime
from data_management.Student import Student
from data_management.BillingDetail import BillingDetail
from data_management.sql_manager import get_engine
from helper.utils import sqlmodel_to_df


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
        


def get_students(student_id: int = None):
    engine = get_engine()

    with Session(engine) as session:
        # Student
        student_sql_statement = select(Student)
        students = []
        if student_id:
            student_sql_statement = student_sql_statement.where(Student.student_id == student_id)
        students = session.exec(student_sql_statement).fetchall()
        return sqlmodel_to_df(students)
