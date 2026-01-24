from typing import Optional
from sqlmodel import Field, Relationship, SQLModel, Session, create_engine, select
from datetime import datetime
from .Student import Student
from .BillingDetail import BillingDetail

engine = create_engine("sqlite:///data_store/database.db")

def get_all_bills(student_id:int):
    with Session(engine) as session:
        # Student
        student_sql_statement = select(Student).where(Student.student_id==student_id)
        student = session.exec(student_sql_statement).first()
        print(student)
        
        # Bills
        bill_sql_statement = select(BillingDetail).where(BillingDetail.student_id==student_id).order_by(BillingDetail.bill_date)
        bills = session.exec(bill_sql_statement).fetchall()
        print(bills)
        
