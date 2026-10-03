"""Base class and reusable validators for DTOs (input and output models)."""
import re
from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict

from helper.clock import today_ist


class DTO(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, from_attributes=True, use_enum_values=True)


def clean_name(value: str) -> str:
    """Collapses inner whitespace; rejects empty names."""
    cleaned = re.sub(r"\s+", " ", value or "").strip()
    if not cleaned:
        raise ValueError("Name is required")
    return cleaned


def blank_to_none(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None


def not_in_future(value: Optional[date]) -> Optional[date]:
    if value is not None and value > today_ist():
        raise ValueError("Date cannot be in the future")
    return value


def one_of(value: Optional[str], allowed, field: str) -> Optional[str]:
    if value is not None and value not in allowed:
        raise ValueError(f"{field} must be one of: {', '.join(map(str, allowed))}")
    return value


def indian_mobile(value: Optional[str]) -> Optional[str]:
    value = blank_to_none(value)
    if value is None:
        return None
    digits = re.sub(r"[\s-]", "", value)
    if digits.startswith("+91"):
        digits = digits[3:]
    if not re.fullmatch(r"[6-9]\d{9}", digits):
        raise ValueError("Mobile number must be 10 digits starting with 6-9")
    return digits
