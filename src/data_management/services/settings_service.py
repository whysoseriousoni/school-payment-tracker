"""School details shown on receipts and reports."""
from typing import Dict

from sqlmodel import select

from data_management.dao import AppSetting
from data_management.sql_manager import session_scope

SCHOOL_NAME = "school_name"
SCHOOL_ADDRESS = "school_address"
SCHOOL_PHONE = "school_phone"

DEFAULTS: Dict[str, str] = {
    SCHOOL_NAME: "School Name (set in Admin > Setup)",
    SCHOOL_ADDRESS: "",
    SCHOOL_PHONE: "",
}


def get_settings() -> Dict[str, str]:
    with session_scope() as session:
        stored = {row.key: row.value for row in session.exec(select(AppSetting))}
    return {**DEFAULTS, **stored}


def save_settings(values: Dict[str, str]) -> None:
    with session_scope() as session:
        for key, value in values.items():
            if key not in DEFAULTS:
                raise ValueError(f"Unknown setting {key}")
            row = session.get(AppSetting, key)
            if row is None:
                session.add(AppSetting(key=key, value=value.strip()))
            else:
                row.value = value.strip()
                session.add(row)
