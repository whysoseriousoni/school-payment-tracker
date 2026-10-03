"""Shared Streamlit helpers: session user, guarded actions, money inputs, flash messages."""
from decimal import Decimal
from typing import Any, Callable, List, Optional

import streamlit as st
from pydantic import ValidationError

from data_management.dto.academic_year import AcademicYearRead
from data_management.dto.user import UserRead
from data_management.services import academic_year_service
from data_management.services.errors import ServiceError
from helper.logger import get_logger
from helper.money import format_inr, rupees_to_paise

logger = get_logger(__name__)

SESSION_USER = "auth_user"
_FLASH = "_flash_messages"
_REQUIRED_TYPES = {"missing", "string_type", "date_type", "int_type", "datetime_type", "model_type"}


# ---------- session / access ----------

def current_user() -> Optional[UserRead]:
    return st.session_state.get(SESSION_USER)


def require_user(admin_only: bool = False) -> UserRead:
    user = current_user()
    if user is None:
        st.warning("Please log in.")
        st.stop()
    if admin_only and not user.is_admin:
        st.error("This page is only available to administrators.")
        st.stop()
    return user


def logout() -> None:
    for key in list(st.session_state.keys()):
        del st.session_state[key]


# ---------- feedback ----------

def flash(message: str, kind: str = "success") -> None:
    """Message shown after the next rerun (st.rerun clears normal output)."""
    st.session_state.setdefault(_FLASH, []).append((kind, message))


def show_flash() -> None:
    for kind, message in st.session_state.pop(_FLASH, []):
        getattr(st, kind)(message)


def validation_messages(error: ValidationError) -> List[str]:
    messages = []
    for item in error.errors():
        field = " > ".join(str(part).replace("_", " ") for part in item["loc"] if not isinstance(part, int))
        text = item["msg"].removeprefix("Value error, ")
        if item.get("input") is None and item["type"] in _REQUIRED_TYPES:
            text = "This field is required"
        messages.append(f"{field.capitalize()}: {text}" if field else text)
    return messages


def error_text(error: Exception) -> str:
    """User-facing text for an error raised by a DTO or service."""
    if isinstance(error, ValidationError):
        return "; ".join(validation_messages(error))
    if isinstance(error, ServiceError):
        return str(error)
    logger.exception("Unexpected error", exc_info=error)
    return "unexpected error (see log)"


def run_action(action: Callable[..., Any], *args, **kwargs) -> Any:
    """Runs a service call and shows friendly errors. Returns None on failure."""
    try:
        return action(*args, **kwargs)
    except ValidationError as error:
        st.error("Please correct the following:\n\n" + "\n".join(f"- {m}" for m in validation_messages(error)))
    except ServiceError as error:
        st.error(str(error))
    except Exception:  # unexpected: log details, show a calm message
        logger.exception("Unexpected error in %s", getattr(action, "__name__", action))
        st.error("Something went wrong. The details were written to the log file; please try again.")
    return None


# ---------- formatting / inputs ----------

def rupees(paise: int) -> str:
    return format_inr(int(paise or 0))


def rupee_input(label: str, key: str, value_paise: int = 0, min_paise: int = 0, **kwargs) -> int:
    value = st.number_input(f"{label} (\u20b9)", min_value=min_paise / 100, value=value_paise / 100,
                            step=100.0, format="%.2f", key=key, **kwargs)
    return rupees_to_paise(Decimal(str(value)))


def page_header(title: str, caption: Optional[str] = None) -> None:
    st.title(title)
    if caption:
        st.caption(caption)
    show_flash()


def term_select(label: str = "Term", key: str = "term", years: Optional[List[AcademicYearRead]] = None,
                default_id: Optional[int] = None) -> Optional[AcademicYearRead]:
    years = years if years is not None else academic_year_service.list_years()
    if not years:
        st.warning("No academic year exists yet. An administrator can add one in Admin > Setup.")
        return None
    if default_id is None:
        default_id = next((y.id for y in years if y.is_current), years[0].id)
    index = next((i for i, y in enumerate(years) if y.id == default_id), 0)
    return st.selectbox(label, years, index=index, key=key,
                        format_func=lambda y: f"{y.label}{' (current)' if y.is_current else ''}")


def optional_select(label: str, options: List[str], key: str, all_label: str = "All") -> Optional[str]:
    choice = st.selectbox(label, [all_label] + list(options), key=key)
    return None if choice == all_label else choice
