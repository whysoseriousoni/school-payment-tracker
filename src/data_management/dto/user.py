import re
from typing import Optional

from pydantic import Field, NaiveDatetime, field_validator

from data_management.dto.common import DTO, one_of
from statics import UserRole

MIN_PASSWORD_LENGTH = 8


def _password_strength(value: str) -> str:
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if not (re.search(r"[A-Za-z]", value) and re.search(r"\d", value)):
        raise ValueError("Password must contain letters and numbers")
    return value


class UserCreate(DTO):
    username: str = Field(min_length=3, max_length=30)
    password: str
    role: str

    _password = field_validator("password")(_password_strength)

    @field_validator("username")
    @classmethod
    def _username(cls, value: str) -> str:
        value = value.lower()
        if not re.fullmatch(r"[a-z0-9_.]+", value):
            raise ValueError("Username may contain only letters, numbers, '_' and '.'")
        return value

    @field_validator("role")
    @classmethod
    def _role(cls, value: str) -> str:
        return one_of(value, [role.value for role in UserRole], "Role")


class PasswordChange(DTO):
    user_id: int
    new_password: str

    _password = field_validator("new_password")(_password_strength)


class UserRead(DTO):
    id: int
    username: str
    role: str
    is_active: bool
    last_login_on: Optional[NaiveDatetime]

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN.value
