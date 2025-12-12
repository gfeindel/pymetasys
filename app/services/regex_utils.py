def normalize_pattern(pattern: str) -> str:
    """
    Normalize user-provided regex strings that may arrive double-escaped
    (e.g. \\d+ in JSON becomes "\\\\d+" in Python). We decode common escapes
    so patterns behave as the user intends.
    """
    try:
        return bytes(pattern, "utf-8").decode("unicode_escape")
    except Exception:
        # Fall back to original if decoding fails
        return pattern
