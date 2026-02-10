"""
Door Se Kaam — File Manager Module

Handles file browsing, upload, and download with path security.
"""

import os
import shutil
import mimetypes
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from config import config


class FileManager:
    """Secure file manager for browsing, uploading, and downloading."""

    def __init__(self):
        mimetypes.init()

    def _is_path_allowed(self, path: str) -> bool:
        """
        Check if a path is within the allowed directories.
        Prevents path traversal attacks.
        """
        try:
            resolved = Path(path).resolve()
            return any(
                str(resolved).startswith(str(Path(d).resolve()))
                for d in config.allowed_directories
            )
        except (ValueError, OSError):
            return False

    def _sanitize_path(self, path: str) -> Optional[Path]:
        """
        Resolve and validate a path. Returns None if invalid or not allowed.
        """
        try:
            resolved = Path(path).resolve()
            if not self._is_path_allowed(str(resolved)):
                return None
            return resolved
        except (ValueError, OSError):
            return None

    def list_directory(self, path: str) -> dict:
        """
        List contents of a directory.

        Returns:
            Dict with 'path', 'parent', and 'items' list
        """
        safe_path = self._sanitize_path(path)
        if safe_path is None:
            return {"error": "Access denied or invalid path"}

        if not safe_path.is_dir():
            return {"error": "Not a directory"}

        items = []
        try:
            for entry in sorted(safe_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
                try:
                    stat = entry.stat()
                    items.append({
                        "name": entry.name,
                        "path": str(entry),
                        "is_dir": entry.is_dir(),
                        "size": stat.st_size if entry.is_file() else 0,
                        "modified": datetime.fromtimestamp(
                            stat.st_mtime
                        ).isoformat(),
                        "mime_type": (
                            mimetypes.guess_type(entry.name)[0]
                            if entry.is_file()
                            else "inode/directory"
                        ),
                    })
                except (PermissionError, OSError):
                    # Skip files we can't access
                    items.append({
                        "name": entry.name,
                        "path": str(entry),
                        "is_dir": entry.is_dir(),
                        "size": 0,
                        "modified": "",
                        "mime_type": "unknown",
                        "error": "Permission denied",
                    })
        except PermissionError:
            return {"error": "Permission denied"}

        # Determine parent path (if within allowed dirs)
        parent = str(safe_path.parent)
        if not self._is_path_allowed(parent):
            parent = None

        return {
            "path": str(safe_path),
            "parent": parent,
            "items": items,
            "total": len(items),
        }

    def get_file_info(self, path: str) -> dict:
        """Get detailed info about a single file."""
        safe_path = self._sanitize_path(path)
        if safe_path is None:
            return {"error": "Access denied or invalid path"}

        if not safe_path.exists():
            return {"error": "File not found"}

        try:
            stat = safe_path.stat()
            return {
                "name": safe_path.name,
                "path": str(safe_path),
                "is_dir": safe_path.is_dir(),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "mime_type": mimetypes.guess_type(safe_path.name)[0],
                "readable": os.access(safe_path, os.R_OK),
                "writable": os.access(safe_path, os.W_OK),
            }
        except (PermissionError, OSError) as e:
            return {"error": str(e)}

    def validate_download(self, path: str) -> tuple:
        """
        Validate a file can be downloaded.

        Returns:
            (Path object, None) on success, or (None, error_message) on failure
        """
        safe_path = self._sanitize_path(path)
        if safe_path is None:
            return None, "Access denied or invalid path"

        if not safe_path.exists():
            return None, "File not found"

        if not safe_path.is_file():
            return None, "Not a file"

        if not os.access(safe_path, os.R_OK):
            return None, "Permission denied"

        return safe_path, None

    def validate_upload(self, filename: str, file_size: int = 0) -> tuple:
        """
        Validate an upload request and return the target path.

        Returns:
            (target_path, None) on success, or (None, error_message) on failure
        """
        # Sanitize filename
        safe_name = Path(filename).name  # strips directory components
        if not safe_name or safe_name.startswith("."):
            return None, "Invalid filename"

        if file_size > config.max_file_size_bytes:
            return None, f"File too large (max {config.max_file_size_bytes // (1024**3)} GB)"

        target_dir = Path(config.upload_directory)
        target_dir.mkdir(parents=True, exist_ok=True)

        target = target_dir / safe_name

        # If file exists, add a suffix
        if target.exists():
            stem = target.stem
            suffix = target.suffix
            counter = 1
            while target.exists():
                target = target_dir / f"{stem}_{counter}{suffix}"
                counter += 1

        return str(target), None

    def get_disk_usage(self) -> dict:
        """Get disk usage info for allowed directories."""
        usage = {}
        for d in config.allowed_directories:
            try:
                total, used, free = shutil.disk_usage(d)
                usage[d] = {
                    "total": total,
                    "used": used,
                    "free": free,
                    "percent_used": round((used / total) * 100, 1),
                }
            except (OSError, FileNotFoundError):
                usage[d] = {"error": "Unable to read"}
        return usage


# Global file manager instance
file_manager = FileManager()
