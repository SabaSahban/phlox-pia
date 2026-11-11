"""Shared sanitization utilities for tool queries.

This module provides sanitization functions to clean queries before sending
to external services, removing potential PHI and other problematic content.
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def sanitize_query_for_external_search(
    query: str, patient_context: dict | None = None
) -> str:
    """Sanitize a search query to prevent leaking PHI to external APIs."""
    if not query:
        return ""

    sanitized = query

    # 1. Strip patient name and UR number if context is provided
    if patient_context:
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

    # 2. General PHI regex patterns (dates, MRNs, phones, emails)
    patterns = [
        r"\b(?:UR|MRN)[\s#:]*\d+\b",
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        r"\b(?:\+?61|0)[2-478](?:[ -]?\d){8}\b",
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    ]
    for pattern in patterns:
        sanitized = re.sub(pattern, "", sanitized, flags=re.IGNORECASE)

    # Clean up excess whitespace
    sanitized = re.sub(r"\s+", " ", sanitized).strip()

    # REMEDIATION (Bug 2): Fail-safe default instead of `or query`
    return sanitized


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
