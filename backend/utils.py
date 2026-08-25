import os
import re


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
