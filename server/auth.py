"""
Door Se Kaam — Authentication Module

Password-based authentication with JWT session tokens.
Includes rate limiting and brute-force lockout.
"""

import time
import hashlib
import secrets
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import jwt, JWTError

from config import config


class AuthManager:
    """Handles password authentication and JWT session management."""

    def __init__(self):
        self._failed_attempts: dict = {}  # ip -> (count, last_time)
        self._load_or_init_password()

    def _load_or_init_password(self):
        """Load password hash from file, or leave empty for first-run setup."""
        if config.password_path.exists():
            self._password_hash = config.password_path.read_text().strip()
        else:
            self._password_hash = ""

    @property
    def is_password_set(self) -> bool:
        return bool(self._password_hash)

    def set_password(self, plain_password: str) -> bool:
        """
        Set or update the server password.

        Args:
            plain_password: The plaintext password to hash and store

        Returns:
            True if successfully set
        """
        if len(plain_password) < 4:
            return False

        hashed = bcrypt.hashpw(
            plain_password.encode("utf-8"),
            bcrypt.gensalt(rounds=12),
        )
        self._password_hash = hashed.decode("utf-8")

        # Persist to disk
        config.password_path.parent.mkdir(parents=True, exist_ok=True)
        config.password_path.write_text(self._password_hash)
        return True

    def verify_password(self, plain_password: str, client_ip: str = "") -> bool:
        """
        Verify a password attempt against the stored hash.
        Implements rate limiting per IP.

        Args:
            plain_password: Password to verify
            client_ip: IP address of the client for rate limiting

        Returns:
            True if password is correct and not rate-limited
        """
        if not self._password_hash:
            return False

        # Check lockout
        if self._is_locked_out(client_ip):
            return False

        try:
            is_valid = bcrypt.checkpw(
                plain_password.encode("utf-8"),
                self._password_hash.encode("utf-8"),
            )
        except Exception:
            is_valid = False

        if is_valid:
            # Clear failed attempts on success
            self._failed_attempts.pop(client_ip, None)
        else:
            # Track failed attempt
            self._record_failure(client_ip)

        return is_valid

    def create_token(self, plain_password: str, client_ip: str = "") -> Optional[str]:
        """
        Authenticate and create a JWT token.

        Returns:
            JWT token string, or None if authentication failed
        """
        if not self.verify_password(plain_password, client_ip):
            return None

        payload = {
            "sub": "remote_user",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc)
            + timedelta(hours=config.jwt_expiry_hours),
            "jti": secrets.token_hex(16),
        }

        return jwt.encode(payload, config.jwt_secret, algorithm="HS256")

    def verify_token(self, token: str) -> bool:
        """Verify a JWT token is valid and not expired."""
        try:
            payload = jwt.decode(
                token, config.jwt_secret, algorithms=["HS256"]
            )
            return payload.get("sub") == "remote_user"
        except JWTError:
            return False

    def get_token_info(self, token: str) -> Optional[dict]:
        """Decode and return token payload, or None if invalid."""
        try:
            return jwt.decode(
                token, config.jwt_secret, algorithms=["HS256"]
            )
        except JWTError:
            return None

    def _is_locked_out(self, client_ip: str) -> bool:
        """Check if a client IP is locked out due to too many failures."""
        if not client_ip or client_ip not in self._failed_attempts:
            return False

        count, last_time = self._failed_attempts[client_ip]
        if count >= config.max_login_attempts:
            elapsed = time.time() - last_time
            if elapsed < config.lockout_duration_seconds:
                return True
            else:
                # Lockout expired — reset
                del self._failed_attempts[client_ip]
                return False
        return False

    def _record_failure(self, client_ip: str):
        """Record a failed login attempt."""
        if not client_ip:
            return

        if client_ip in self._failed_attempts:
            count, _ = self._failed_attempts[client_ip]
            self._failed_attempts[client_ip] = (count + 1, time.time())
        else:
            self._failed_attempts[client_ip] = (1, time.time())

    def get_lockout_remaining(self, client_ip: str) -> int:
        """Return seconds remaining in lockout, or 0 if not locked out."""
        if not client_ip or client_ip not in self._failed_attempts:
            return 0

        count, last_time = self._failed_attempts[client_ip]
        if count >= config.max_login_attempts:
            elapsed = time.time() - last_time
            remaining = config.lockout_duration_seconds - elapsed
            return max(0, int(remaining))
        return 0


# Global auth manager instance
auth_manager = AuthManager()
