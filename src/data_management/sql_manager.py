import sqlite3
import os
from sqlmodel import Field, Relationship, SQLModel, Session, create_engine
import streamlit as st


@st.cache_resource
def get_engine():
    # This runs ONCE and the 'engine' is stored in memory
    try:
        return create_engine("sqlite:///data_store/database.db")
    except:
        raise RuntimeError("Unable to connect to SQLite engine")

@st.cache_resource
def create_and_register_sqlite():
    """
    Creates new database + Skeleton of tables
    """
    # Add more SQL Models here
    from data_management.Student import Student
    from data_management.BillingDetail import BillingDetail

    Student.model_rebuild()
    BillingDetail.model_rebuild()
    # End of adding model registries
    
    # Create if not exist:
    engine = get_engine()
    SQLModel.metadata.create_all(engine)

def clone_sqlite_file(source_file_name, destination_file_name, backup_location=r"src\backup_and_restore", ):
    __source_connection__ = sqlite3.connect(source_file_name)
    __destination_connection__ = sqlite3.connect(f"{backup_location}\\{destination_file_name}")
    try:
        with __destination_connection__:
            __source_connection__.backup(__destination_connection__, pages=-1)
    except sqlite3.Error as e:
        print(f"SQLite error during backup: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        if __source_connection__:
            __source_connection__.close()
        if __destination_connection__:
            __destination_connection__.close()


# def get_connector(file_name, database_name):
#     __connection__ = sqlite3.connect(database=database_name)
#     return __connection__

