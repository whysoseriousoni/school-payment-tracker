from typing import Optional

from sqlmodel import Field

from data_management.dao.base import TimestampMixin


class Identifier(TimestampMixin, table=True):
    """
    Government identifier (Aadhaar) encrypted with AES-GCM (AEAD).
    `ciphertext` includes the authentication tag; both it and `nonce` are
    base64 text. Both are NULL when only the last 4 digits are known.
    """

    __tablename__ = "identifier"

    id: Optional[int] = Field(default=None, primary_key=True)
    identifier_type: str
    ciphertext: Optional[str] = None
    nonce: Optional[str] = None
    last_4_digits: str
    key_version: int = Field(default=1)
    fingerprint: Optional[str] = Field(default=None, unique=True)  # HMAC, for duplicate checks
