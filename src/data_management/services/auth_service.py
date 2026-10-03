"""Accounts and password checks (bcrypt). Plain passwords are never stored or logged."""
from typing import List, Optional

import bcrypt
from sqlmodel import select

from data_management.dao import AppUser
from data_management.dto.user import PasswordChange, UserCreate, UserRead
from data_management.services.errors import BusinessRuleError, NotFoundError
from data_management.sql_manager import session_scope
from helper.clock import now_ist
from helper.logger import get_logger
from statics import UserRole

logger = get_logger(__name__)

# Spend similar time for unknown users so response time does not reveal valid usernames.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt()).decode("ascii")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


def _by_username(session, username: str) -> Optional[AppUser]:
    return session.exec(select(AppUser).where(AppUser.username == username.strip().lower())).first()


def needs_first_admin() -> bool:
    with session_scope() as session:
        return session.exec(
            select(AppUser).where(AppUser.role == UserRole.ADMIN.value, AppUser.is_active == True)  # noqa: E712
        ).first() is None


def authenticate(username: str, password: str) -> Optional[UserRead]:
    with session_scope() as session:
        user = _by_username(session, username or "")
        if user is None or not user.is_active:
            verify_password(password or "", _DUMMY_HASH)
            logger.info("Failed login for %r", username)
            return None
        if not verify_password(password or "", user.password_hash):
            logger.info("Failed login for %r", username)
            return None
        user.last_login_on = now_ist()
        session.add(user)
        session.flush()
        logger.info("User %s logged in", user.username)
        return UserRead.model_validate(user)


def create_user(data: UserCreate) -> UserRead:
    with session_scope() as session:
        if _by_username(session, data.username):
            raise BusinessRuleError(f"Username '{data.username}' is already taken")
        user = AppUser(username=data.username, password_hash=hash_password(data.password), role=data.role)
        session.add(user)
        session.flush()
        logger.info("Created user %s (%s)", user.username, user.role)
        return UserRead.model_validate(user)


def create_first_admin(data: UserCreate) -> UserRead:
    if not needs_first_admin():
        raise BusinessRuleError("An administrator already exists")
    if data.role != UserRole.ADMIN.value:
        raise BusinessRuleError("The first account must be an administrator")
    return create_user(data)


def list_users() -> List[UserRead]:
    with session_scope() as session:
        return [UserRead.model_validate(user) for user in session.exec(select(AppUser).order_by(AppUser.username))]


def change_password(data: PasswordChange) -> None:
    with session_scope() as session:
        user = session.get(AppUser, data.user_id)
        if user is None:
            raise NotFoundError("User not found")
        user.password_hash = hash_password(data.new_password)
        session.add(user)


def set_active(user_id: int, active: bool, acting_user_id: int) -> None:
    with session_scope() as session:
        user = session.get(AppUser, user_id)
        if user is None:
            raise NotFoundError("User not found")
        if user_id == acting_user_id and not active:
            raise BusinessRuleError("You cannot deactivate your own account")
        if not active and user.role == UserRole.ADMIN.value:
            other_admins = session.exec(
                select(AppUser).where(AppUser.role == UserRole.ADMIN.value, AppUser.is_active == True,  # noqa: E712
                                      AppUser.id != user_id)
            ).first()
            if other_admins is None:
                raise BusinessRuleError("At least one active administrator is required")
        user.is_active = active
        session.add(user)
