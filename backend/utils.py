import os
import re
from fastapi import HTTPException

# Nothing legitimately uploaded to this app (a PQ form, a compliance
# certificate, a project register) should ever approach this size. Without
# a cap, an unauthenticated-in-practice (shared key, shipped in the
# frontend bundle) endpoint accepting uploads is an easy disk/memory
# exhaustion vector once this is reachable from the internet.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25MB


def enforce_upload_size(num_bytes: int, max_bytes: int = MAX_UPLOAD_BYTES):
    if num_bytes > max_bytes:
        raise HTTPException(413, f"File too large (max {max_bytes // (1024 * 1024)}MB)")


def normalize_field_key(field_label: str) -> str:
    """
    Standardizes how field labels are converted to database keys.
    Lowercase, replace spaces and slashes with underscores, and limit to 100 characters.
    """
    if not field_label:
        return ""
    return str(field_label).strip().lower().replace(" ", "_").replace("/", "_")[:100]


def sanitize_filename(filename: str) -> str:
    """
    Strips any directory components (including Windows-style backslashes, which
    os.path.basename alone won't catch on POSIX) and replaces anything that
    isn't alphanumeric/dot/dash/underscore. Prevents an uploaded filename like
    "../../etc/passwd" or "..\\..\\config.py" from escaping the intended
    upload directory when later joined with os.path.join(UPLOAD_DIR, filename).
    """
    name = os.path.basename((filename or "").replace("\\", "/"))
    name = re.sub(r'[^\w.\-]', '_', name).strip('._') or "upload"
    return name[:200]
