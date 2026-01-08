from __future__ import annotations

import os
from typing import Optional

from fastapi import Request


def to_public_url(value: Optional[str], request: Optional[Request] = None) -> Optional[str]:
    """Convert stored relative upload paths (e.g. /uploads/...) to a public absolute URL.

    - If `PUBLIC_BASE_URL` is set, it is used as the base.
    - Otherwise, if a `request` is provided, `request.base_url` is used.
    - If `value` is already absolute (http/https), it is returned as-is.
    """

    if not value:
        return None

    if value.startswith("http://") or value.startswith("https://"):
        return value

    base = (os.getenv("PUBLIC_BASE_URL") or "").strip()
    if not base and request is not None:
        base = str(request.base_url)

    if not base:
        # No way to build an absolute URL; keep legacy behavior.
        return value

    base = base.rstrip("/")
    path = value if value.startswith("/") else f"/{value}"
    return f"{base}{path}"
