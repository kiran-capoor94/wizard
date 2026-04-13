import logging

logger = logging.getLogger(__name__)

# Pass 1: exact names to wizard field mapping (lowercase)
_EXACT_NAMES: dict[str, str] = {
    "task": "task_name",
    "status": "task_status",
    "priority": "task_priority",
    "due date": "task_due_date",
    "jira": "task_jira_key",
    "meeting name": "meeting_title",
    "date": "meeting_date",
    "krisp url": "meeting_url",
    "summary": "meeting_summary",
}

# Pass 2: property type hints — first property of matching type wins
_TYPE_HINTS: dict[str, str] = {
    "task_name": "title",
    "meeting_title": "title",
    "task_due_date": "date",
    "meeting_date": "date",
}

# Pass 3: synonyms
_SYNONYMS: dict[str, list[str]] = {
    "task_status": ["state", "workflow", "stage"],
    "meeting_url": ["recording", "transcript", "krisp", "fathom", "video", "transcript url", "fathom url", "krisp url"],
}


def fetch_db_properties(notion_client, db_id: str) -> dict[str, str]:
    """Return {property_name: property_type} for the given DB."""
    try:
        response = notion_client.databases.retrieve(database_id=db_id)
        return {
            name: prop["type"]
            for name, prop in response.get("properties", {}).items()
        }
    except Exception as exc:
        logger.warning("notion_discovery fetch_db_properties failed for %s: %s", db_id, exc)
        return {}


def match_properties(
    available: dict[str, str],
    fields: list[str],
) -> dict[str, str | None]:
    """Map wizard field names to Notion property names using 3-pass matching.

    Returns {wizard_field: matched_property_name_or_None}
    """
    result: dict[str, str | None] = {}
    available_lower = {k.lower(): k for k in available}

    for field in fields:
        matched = None

        # Pass 1: exact name match (case-insensitive)
        for prop_lower, prop_original in available_lower.items():
            if _EXACT_NAMES.get(prop_lower) == field:
                matched = prop_original
                break

        # Pass 2: type match
        if matched is None and field in _TYPE_HINTS:
            target_type = _TYPE_HINTS[field]
            for prop_name, prop_type in available.items():
                if prop_type == target_type:
                    matched = prop_name
                    break

        # Pass 3: synonym match
        if matched is None and field in _SYNONYMS:
            synonyms = _SYNONYMS[field]
            for synonym in synonyms:
                if synonym in available_lower:
                    matched = available_lower[synonym]
                    break

        result[field] = matched

    return result
