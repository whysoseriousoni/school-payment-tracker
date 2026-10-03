"""
Aadhaar protection using AES-256-GCM (Authenticated Encryption with Associated Data).

* The 32-byte master key lives in secrets/identifier.key (base64), or in the
  SPT_IDENTIFIER_KEY environment variable. It is created on first use.
* Associated data binds each ciphertext to its student and identifier type, so a
  ciphertext copied onto another student fails authentication.
* A keyed HMAC "fingerprint" detects duplicate numbers without decrypting.
* Without the key, stored numbers are unrecoverable: back the key up separately.
"""
import base64
import hashlib
import hmac
import os
import re
from pathlib import Path
from typing import Optional, Tuple

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from config import settings
from helper.logger import get_logger

logger = get_logger(__name__)

KEY_VERSION = 1
_NONCE_BYTES = 12

# Verhoeff checksum tables (Aadhaar's last digit is a Verhoeff check digit).
_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


class IdentifierKeyError(RuntimeError):
    """The encryption key is missing, unreadable or wrong."""


def verhoeff_is_valid(number: str) -> bool:
    check = 0
    for position, digit in enumerate(reversed(number)):
        check = _D[check][_P[position % 8][int(digit)]]
    return check == 0


def normalise_aadhaar(raw: str) -> str:
    """Strips spaces/hyphens and validates format + checksum. Raises ValueError."""
    digits = re.sub(r"[\s-]", "", raw or "")
    if not re.fullmatch(r"\d{12}", digits):
        raise ValueError("Aadhaar number must have exactly 12 digits")
    if digits[0] in "01":
        raise ValueError("Aadhaar number cannot start with 0 or 1")
    if not verhoeff_is_valid(digits):
        raise ValueError("Aadhaar number checksum failed - please re-check the digits")
    return digits


def mask(last_4_digits: Optional[str]) -> str:
    return f"XXXX XXXX {last_4_digits}" if last_4_digits else "-"


# ---------- key management ----------

def key_path() -> Path:
    return Path(os.environ.get("SPT_IDENTIFIER_KEY_PATH", settings.IDENTIFIER_KEY_PATH))


def _load_or_create_master_key() -> bytes:
    from_env = os.environ.get("SPT_IDENTIFIER_KEY")
    if from_env:
        key = base64.b64decode(from_env)
    else:
        path = key_path()
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(base64.b64encode(AESGCM.generate_key(bit_length=256)).decode("ascii"), encoding="ascii")
            logger.warning("Created new identifier encryption key at %s - BACK IT UP SEPARATELY", path)
        key = base64.b64decode(path.read_text(encoding="ascii").strip())
    if len(key) != 32:
        raise IdentifierKeyError("Identifier key must be 32 bytes (base64 encoded)")
    return key


def key_fingerprint() -> str:
    """Short, non-secret ID of the current key (to match a key file with its database)."""
    return hashlib.sha256(_load_or_create_master_key()).hexdigest()[:16]


def _derive(info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(_load_or_create_master_key())


# ---------- operations ----------

def _associated_data(student_id: int, identifier_type: str) -> bytes:
    return f"student:{student_id}|type:{identifier_type}|v{KEY_VERSION}".encode("utf-8")


def encrypt(number: str, student_id: int, identifier_type: str) -> Tuple[str, str]:
    """Returns (ciphertext_b64, nonce_b64); the ciphertext includes the GCM tag."""
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(_derive(b"identifier-encryption")).encrypt(
        nonce, number.encode("utf-8"), _associated_data(student_id, identifier_type)
    )
    return base64.b64encode(ciphertext).decode("ascii"), base64.b64encode(nonce).decode("ascii")


def decrypt(ciphertext_b64: str, nonce_b64: str, student_id: int, identifier_type: str) -> str:
    try:
        plain = AESGCM(_derive(b"identifier-encryption")).decrypt(
            base64.b64decode(nonce_b64), base64.b64decode(ciphertext_b64),
            _associated_data(student_id, identifier_type),
        )
    except Exception as error:  # InvalidTag and decoding errors
        raise IdentifierKeyError("Could not decrypt identifier: wrong key or tampered data") from error
    return plain.decode("utf-8")


def fingerprint(number: str, identifier_type: str) -> str:
    return hmac.new(_derive(b"identifier-fingerprint"), f"{identifier_type}:{number}".encode("utf-8"),
                    hashlib.sha256).hexdigest()
