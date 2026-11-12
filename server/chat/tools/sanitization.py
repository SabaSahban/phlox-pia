"""Shared sanitization utilities for tool queries.

This module provides sanitization functions to clean queries before sending
to external services, removing potential PHI and other problematic content.
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# Named PHI rules, applied in order. Names are logged; matched text never is.
_PHI_RULES: list[tuple[str, re.Pattern[str]]] = [
    # UR numbers (various formats)
    ("ur_number", re.compile(r"\bUR\s*[:#]?\s*\d{4,}\b", re.IGNORECASE)),
    ("ur_number", re.compile(r"\bUR\s*[:#]?\s*[A-Z]?\d{4,}[A-Z]?\b", re.IGNORECASE)),
    # Medical record numbers
    ("mrn", re.compile(r"\bMRN\s*[:#]?\s*\d+\b", re.IGNORECASE)),
    # Dates of birth (various formats)
    ("date", re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")),
    ("date", re.compile(r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b")),
    # Phone numbers
    ("phone", re.compile(r"\b(?:\+?61|0)[2-478](?:[ -]?\d){8}\b", re.IGNORECASE)),
    ("phone", re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    ("phone", re.compile(r"\b\+?\d{1,3}[-.\s]?\d{2,4}[-.\s]?\d{3,4}[-.\s]?\d{4}\b")),
    # Australian formats (mobile 04XX XXX XXX, landline 0X XXXX XXXX)
    ("phone", re.compile(r"\b0?4\d{2}[-.\s]?\d{3}[-.\s]?\d{3}\b")),
    ("phone", re.compile(r"\b0\d[-.\s]?\d{4}[-.\s]?\d{4}\b")),
    # Email addresses
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")),
    # Addresses (simple pattern for street addresses)
    (
        "address",
        re.compile(
            r"\b\d+\s+[A-Za-z]+\s+(Street|St|Avenue|Ave|Road|Rd|Lane|Ln|Drive|Dr|Court|Ct|Place|Pl)\b",
            re.IGNORECASE,
        ),
    ),
    # Medicare/health card numbers (Australian format)
    ("medicare", re.compile(r"\b\d{4}\s?\d{4,5}\s?\d{1,2}\b")),
]


def sanitize_query_for_external_search(
    query: str, patient_context: dict[str, Any] | None = None
) -> str:
    """Remove potential PHI from search queries before sending to external services.

    This is a defense-in-depth measure to prevent accidental PHI leakage even if
    the LLM includes it in search queries despite prompt instructions.

    Args:
        query: The original search query
        patient_context: Optional dict with patient info to specifically remove
            (ur_number, name, etc.)

    Returns:
        Sanitized query string with PHI patterns removed
    """
    if not query:
        return ""

    sanitized = query
    fired: list[str] = []

    # Remove common PHI patterns (order matters; see _PHI_RULES)
    for rule_name, pattern in _PHI_RULES:
        sanitized, count = pattern.subn("", sanitized)
        if count and rule_name not in fired:
            fired.append(rule_name)

    # Remove specific patient context if provided
    if patient_context:
        before_context = sanitized
        name = patient_context.get("name")
        if name:
            for name_part in name.split():
                if len(name_part) <= 1:
                    continue
                sanitized = re.sub(
                    rf"\b{re.escape(name_part)}\b", "", sanitized, flags=re.IGNORECASE
                )
        ur_number = patient_context.get("ur_number")
        if ur_number:
            sanitized = re.sub(
                rf"\b{re.escape(str(ur_number))}\b",
                "",
                sanitized,
                flags=re.IGNORECASE,
            )
        if sanitized != before_context:
            fired.append("patient_context")

    # Clean up extra whitespace and punctuation
    sanitized = re.sub(r"\s+", " ", sanitized)
    sanitized = re.sub(r"^[\s,-]+|[\s,-]+$", "", sanitized)

    if sanitized != query:
        # Metadata only: never log query text (names survive the regex rules).
        logger.info(
            "Sanitized search query: rules=%s, length %d -> %d",
            ",".join(fired) or "whitespace",
            len(query),
            len(sanitized),
        )

    return sanitized.strip()


def sanitize_pubmed_query(
    query: str, patient_context: dict[str, Any] | None = None
) -> str:
    """Sanitize a PubMed query: strip PHI, then remove standalone years.



    Args:
        query: The raw search query

    Returns:
        Sanitized query with PHI patterns and standalone years removed
    """

    if not query:
        return ""

    sanitized = sanitize_query_for_external_search(
        query, patient_context=patient_context
    )

    sanitized = re.sub(r"\b(19|20)\d{2}\b", "", sanitized)

    # Clean up extra whitespace that may result from removal
    sanitized = re.sub(r"\s+", " ", sanitized).strip()

    return sanitized
