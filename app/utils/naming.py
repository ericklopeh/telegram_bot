def sanitize_name(text: str) -> str:
    invalid_chars = '<>:"/\\|?*'
    cleaned = "".join("_" if c in invalid_chars else c for c in text.strip())
    return " ".join(cleaned.split())
