import sqlite3
import os


def create_new_sqlite(file_name):
    sqlite3.connect(database="")

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


def get_connector(file_name, database_name):
    __connection__ = sqlite3.connect(database=database_name)
    return __connection__

