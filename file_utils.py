"""Helpers for safely handling uploaded files."""

import os
from pathlib import Path


def safe_upload_path(upload_dir: str | Path, filename: str | None) -> Path:
    """Return a safe absolute path inside upload_dir for the given filename.

    Raises ValueError if the resolved path would escape upload_dir.
    """
    if not filename:
        raise ValueError("filename is required")

    # Remove any directory components and risky characters
    safe_name = os.path.basename(filename)
    safe_name = safe_name.replace("\\", "_").replace("/", "_")
    if not safe_name or safe_name in {".", ".."}:
        raise ValueError("invalid filename")

    upload_dir = Path(upload_dir).resolve()
    target = (upload_dir / safe_name).resolve()

    # Ensure the resolved target stays inside upload_dir
    try:
        target.relative_to(upload_dir)
    except ValueError as exc:
        raise ValueError("filename attempts to escape upload directory") from exc

    return target
