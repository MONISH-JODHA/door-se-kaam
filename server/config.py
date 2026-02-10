"""
Door Se Kaam — Configuration Module

Central configuration for the remote desktop server using environment
variables and sensible defaults.
"""

import os
import secrets
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class ServerConfig:
    """Server configuration with sensible defaults."""

    # ── Network ──────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8443
    use_https: bool = True

    # ── Authentication ───────────────────────────────────────
    # Password is set on first run or via env var
    password_hash: str = ""
    jwt_secret: str = field(default_factory=lambda: secrets.token_hex(32))
    jwt_expiry_hours: int = 24
    max_login_attempts: int = 5
    lockout_duration_seconds: int = 300  # 5 minutes

    # ── Screen Capture ───────────────────────────────────────
    capture_fps: int = 15
    capture_quality: int = 60  # JPEG quality 1-100
    capture_monitor: int = 0  # 0 = all monitors, 1+ = specific
    max_fps: int = 30
    min_quality: int = 20

    # ── Input ────────────────────────────────────────────────
    default_sensitivity: float = 1.0

    # ── File Transfer ────────────────────────────────────────
    allowed_directories: list = field(default_factory=lambda: [
        str(Path.home()),
    ])
    max_file_size_bytes: int = 2 * 1024 * 1024 * 1024  # 2 GB
    upload_directory: str = field(
        default_factory=lambda: str(Path.home() / "DoorSeKaam_Uploads")
    )

    # ── TLS Certificates ────────────────────────────────────
    cert_dir: str = field(
        default_factory=lambda: str(
            Path(__file__).parent / "certs"
        )
    )
    cert_file: str = "server.crt"
    key_file: str = "server.key"

    # ── Paths ────────────────────────────────────────────────
    data_dir: str = field(
        default_factory=lambda: str(
            Path(__file__).parent / "data"
        )
    )
    password_file: str = "password.hash"

    @property
    def cert_path(self) -> Path:
        return Path(self.cert_dir) / self.cert_file

    @property
    def key_path(self) -> Path:
        return Path(self.cert_dir) / self.key_file

    @property
    def password_path(self) -> Path:
        return Path(self.data_dir) / self.password_file

    def ensure_directories(self):
        """Create required directories if they don't exist."""
        Path(self.cert_dir).mkdir(parents=True, exist_ok=True)
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        Path(self.upload_directory).mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "ServerConfig":
        """Create config from environment variables with defaults."""
        config = cls()

        # Override from env vars
        config.host = os.getenv("DSK_HOST", config.host)
        config.port = int(os.getenv("DSK_PORT", str(config.port)))
        config.capture_fps = int(os.getenv("DSK_FPS", str(config.capture_fps)))
        config.capture_quality = int(
            os.getenv("DSK_QUALITY", str(config.capture_quality))
        )
        config.capture_monitor = int(
            os.getenv("DSK_MONITOR", str(config.capture_monitor))
        )
        config.jwt_expiry_hours = int(
            os.getenv("DSK_JWT_EXPIRY", str(config.jwt_expiry_hours))
        )

        env_dirs = os.getenv("DSK_ALLOWED_DIRS")
        if env_dirs:
            config.allowed_directories = [
                d.strip() for d in env_dirs.split(",") if d.strip()
            ]

        config.ensure_directories()
        return config


# Global config instance
config = ServerConfig.from_env()
