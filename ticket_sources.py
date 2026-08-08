"""Helpers for safely ordering interchange ticket source filenames."""


def ordered_ticket_sources(first, second):
    """Return nullable source names with the OUT ticket first when identifiable."""
    first = first or ""
    second = second or ""
    if "IN" in first:
        return second, first
    return first, second
