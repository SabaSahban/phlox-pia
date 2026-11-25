"""
This test file is for the sanitization pipeline. It only tests the in-memory logic.
"""

import importlib.util
from pathlib import Path

# load server/chat/tools/sanitization.py directly without triggering application init
# triggering __init__.py results in creation of sqlite3 database, which is not needed for our simple test
_spec = importlib.util.spec_from_file_location(
    "sanitization",
    Path(__file__).parent / "server/chat/tools/sanitization.py",
)
_sanitization = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sanitization)

sanitize_pubmed_query = _sanitization.sanitize_pubmed_query
sanitize_query_for_external_search = _sanitization.sanitize_query_for_external_search


def test_1():
    """
    this test proves that `sanitize_query_for_external_search` can strip names if patient_context is explicitly passed to it.
    """

    query = "lower back spasm treatment options for Rafa Galvez"
    patient_context = {"name": "Rafa Galvez", "ur_number": "123456"}
    result = sanitize_query_for_external_search(query, patient_context=patient_context)

    print(f"\n[Test 1 - Testing Sanitization Pipeline, Given `patient_context`]")
    print("-" * 30)
    print(f"  Input:  '{query}'")
    print(f"  Output: '{result}'")

    assert "Rafa" not in result
    assert "Galvez" not in result
    assert result == "lower back spasm treatment options for"


def test_2():
    """
    this tests whether the name is removed from the query, if the patient context is not passed to the sanitization pipeline.
    """

    query = "lower back spasm treatment options for Rafa Galvez"
    result = sanitize_query_for_external_search(query)

    print(f"\n[Test 2 - Testing Sanitization Pipeline, without 'patient_context')]")
    print("-" * 30)
    print(f"  Input:  '{query}'")
    print(f"  Output: '{result}'")

    assert "Rafa Galvez" in result


def test_3():
    """
    test the `sanitize_pubmed_query` function. this function doesn't even take the `patient_context` as argument.
    """

    query = "lower back pain treatment options for Rafa Galvez 2023"
    result = sanitize_pubmed_query(query)

    print(f"\n[Test 3 - PubMed Search Call]")
    print("-" * 30)
    print(f"  Input:  '{query}'")
    print(f"  Output: '{result}'")

    assert "2023" not in result
    assert "Rafa Galvez" in result


"""
now checking the scenario when the query might contain only tokens such as patient UR number, contact, etc. (anything but the name of the patient)"
This scenario may happen, when a doctor uses Phlox to see if there are public medical record of a patient is available.
"""


def test_4():
    """
    When a query consists purely of tokens that the regexes completely remove, 'sanitized.strip()' becomes empty string, and the fallback
    returns the raw, unredacted string.
    """

    pure_phi_query = "UR 1234567 14/05/1978 0490 20 20 20"
    result = sanitize_query_for_external_search(pure_phi_query)

    print(f"\n[Test 4 - Pure PHI Fallback Bug]")
    print("-" * 30)
    print(f"  Input:  '{pure_phi_query}'")
    print(f"  Output: '{result}'")

    assert result == pure_phi_query


def test_5():
    """
    If `patient_context` is provided but the query consists only of the patient's name, it turns into an empty string,
    which then the sanitization pipeline returns the original, unredacted query.
    """

    name_only_query = "Rafa Galvez"
    patient_context = {"name": "Rafa Galvez"}

    result = sanitize_query_for_external_search(
        name_only_query, patient_context=patient_context
    )

    print(f"\n[Test 5 - Name-Only Fallback Bug]")
    print("-" * 30)
    print(f"  Input:  '{name_only_query}'")
    print(f"  Output: '{result}'")

    assert result == "Rafa Galvez"
