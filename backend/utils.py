def normalize_field_key(field_label: str) -> str:
    """
    Standardizes how field labels are converted to database keys.
    Lowercase, replace spaces and slashes with underscores, and limit to 100 characters.
    """
    if not field_label:
        return ""
    return str(field_label).strip().lower().replace(" ", "_").replace("/", "_")[:100]
