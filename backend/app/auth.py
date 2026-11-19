import hashlib
import hmac
import json
import re
import secrets
from typing import Any


PASSWORD_HASH_ITERATIONS = 600_000
MIN_PASSWORD_HASH_ITERATIONS = 200_000
MAX_PASSWORD_HASH_ITERATIONS = 1_000_000
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")


def hash_password(password: str, salt: bytes | None = None) -> str:
    if len(password) < 12:
        raise ValueError("Passwords must contain at least 12 characters.")
    password_salt = salt or secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), password_salt, PASSWORD_HASH_ITERATIONS
    )
    return (
        f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}"
        f"${password_salt.hex()}${password_hash.hex()}"
    )


def parse_password_hash(encoded_hash: str) -> tuple[int, bytes, bytes] | None:
    try:
        algorithm, iteration_text, salt_text, expected_text = encoded_hash.split("$")
        iterations = int(iteration_text)
        salt = bytes.fromhex(salt_text)
        expected = bytes.fromhex(expected_text)
    except (ValueError, TypeError):
        return False
    if (
        algorithm != "pbkdf2_sha256"
        or not MIN_PASSWORD_HASH_ITERATIONS <= iterations <= MAX_PASSWORD_HASH_ITERATIONS
        or len(salt) != 16
        or len(expected) != 32
    ):
        return None
    return iterations, salt, expected


def verify_password(password: str, encoded_hash: str) -> bool:
    if len(password) > 1024:
        return False
    parsed_hash = parse_password_hash(encoded_hash)
    if parsed_hash is None:
        return False
    iterations, salt, expected = parsed_hash

    actual = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    return hmac.compare_digest(actual, expected)


def load_users(raw_users: str, account_count: int) -> dict[str, dict[str, Any]]:
    try:
        entries = json.loads(raw_users)
    except json.JSONDecodeError as error:
        raise ValueError("PHARMACHAIN_USERS_JSON must contain a valid JSON array.") from error
    if not isinstance(entries, list) or len(entries) < 3:
        raise ValueError(
            "Configure at least three users: administrator, manufacturer, and distributor."
        )

    users: dict[str, dict[str, Any]] = {}
    account_indices: set[int] = set()
    administrator_count = 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Each configured user must be a JSON object.")
        username = entry.get("username")
        password_hash = entry.get("passwordHash")
        account_index = entry.get("accountIndex")
        if not isinstance(username, str) or not USERNAME_PATTERN.fullmatch(username):
            raise ValueError(
                "Usernames must be 3-64 letters, numbers, dots, underscores, or hyphens."
            )
        if username in users:
            raise ValueError("Configured usernames must be unique.")
        if not isinstance(password_hash, str) or parse_password_hash(password_hash) is None:
            raise ValueError(
                f"User {username!r} has an invalid passwordHash; generate a PBKDF2 hash "
                "with scripts/hash_password.py."
            )
        if (
            isinstance(account_index, bool)
            or not isinstance(account_index, int)
            or not 0 <= account_index < account_count
        ):
            raise ValueError(
                f"User {username!r} accountIndex must be between 0 and {account_count - 1}."
            )
        if account_index in account_indices:
            raise ValueError("Each configured user must have a unique accountIndex.")

        if account_index == 0:
            administrator_count += 1
        account_indices.add(account_index)
        users[username] = {
            "username": username,
            "passwordHash": password_hash,
            "accountIndex": account_index,
        }

    if administrator_count != 1:
        raise ValueError("Exactly one configured user must use accountIndex 0 (administrator).")
    return users
