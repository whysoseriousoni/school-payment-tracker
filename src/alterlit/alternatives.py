from datetime import datetime
from functools import partial
import streamlit as st


def reset_date(key, default_value):
    if default_value in {"today"}:
        default_value = datetime.now().date()
    st.session_state[key] = default_value
    st.toast("Date field reset successfully")


def date_input(key, label, default_value="today", max_value=None, *args, **kwargs):
    date_field_column, default_field_column = st.columns([0.9, 0.1])
    with date_field_column:
        value = st.date_input(
            label=label,
            key=key,
            value=default_value,
            format="YYYY/MM/DD",
            min_value="1980-01-01",
            max_value=max_value,
        )
    with default_field_column:
        st.text("")
        st.text("")
        st.button(
            label="X",
            key=f"{key}_delete_date_input",
            on_click=partial(reset_date, key, default_value),
        )
    return value
