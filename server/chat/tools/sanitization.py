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
    query: str, patient_context: dict | None = None
) -> str:
    """Sanitize a search query to prevent leaking PHI to external APIs."""
    if not query:
        return ""

    sanitized = query
    fired: list[str] = []

    # 1. Remove common PHI patterns (order matters; see _PHI_RULES)
    for rule_name, pattern in _PHI_RULES:
        sanitized, count = pattern.subn("", sanitized)
        if count and rule_name not in fired:
            fired.append(rule_name)

    # 2. Strip patient name and UR number if context is provided
    if patient_context:
        before_context = sanitized

        name = patient_context.get("name")
        if name:
            for part in name.split():
                if len(part) > 1:
                    sanitized = re.sub(
                        rf"\b{re.escape(part)}\b", "", sanitized, flags=re.IGNORECASE
                    )

        ur_number = patient_context.get("ur_number")
        if ur_number:
            sanitized = re.sub(
                rf"\b{re.escape(str(ur_number))}\b", "", sanitized, flags=re.IGNORECASE
            )

        if sanitized != before_context and "patient_context" not in fired:
            fired.append("patient_context")

    # 2. General PHI regex patterns (dates, MRNs, phones, emails)
    patterns = [
        r"\b(?:UR|MRN)[\s#:]*\d+\b",
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        r"\b(?:\+?61|0)[2-478](?:[ -]?\d){8}\b",
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    ]
    for pattern in patterns:
        sanitized = re.sub(pattern, "", sanitized, flags=re.IGNORECASE).strip()

    if sanitized != query:
        # Metadata only: never log query text (names survive the regex rules).
        logger.info(
            "Sanitized search query: rules=%s, length %d -> %d",
            ",".join(fired) or "whitespace",
            len(query),
            len(sanitized),
        )

    return sanitized  # Return original if sanitization empties it


def sanitize_pubmed_query(query: str, patient_context: dict | None = None) -> str:
    """Sanitize a PubMed search query, removing PHI and non-MeSH metadata."""
    if not query:
        return ""

    # REMEDIATION (Bug 1): Run standard PHI sanitization with patient_context first
    sanitized = sanitize_query_for_external_search(
        query, patient_context=patient_context
    )

    # PubMed-specific stripping (e.g., bare 4-digit years)
    sanitized = re.sub(r"\b(19|20)\d{2}\b", "", sanitized)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()

    # Fail-safe return
    return sanitized
