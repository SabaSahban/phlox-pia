import asyncio
import importlib.util
from pathlib import Path
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _load_search_modules():
    """
    Import `sanitization`, `wiki_search` and `pubmed_search` without booting
    the whole app.

    A normal import would run every __init__.py on the way down (server/,
    server/chat/, ...), which pulls in the real application. So instead we
    fake those packages and load just the files we want to test, with their
    heavier dependencies swapped for mocks.

    Returns (`san_mod`, `wiki_mod`, `pubmed_mod`).
    """

    pkg_paths = [
        ("server", Path(__file__).parent / "server"),
        ("server.chat", Path(__file__).parent / "server/chat"),
        ("server.chat.tools", Path(__file__).parent / "server/chat/tools"),
        ("server.chat.streaming", Path(__file__).parent / "server/chat/streaming"),
        ("server.chat.models", Path(__file__).parent / "server/chat/models"),
    ]

    for mod_name, mod_path in pkg_paths:
        if mod_name not in sys.modules:
            m = types.ModuleType(mod_name)
            m.__path__ = [str(mod_path)]
            sys.modules[mod_name] = m

    # load sanitization.py
    san_spec = importlib.util.spec_from_file_location(
        "server.chat.tools.sanitization",
        Path(__file__).parent / "server/chat/tools/sanitization.py",
    )
    san_mod = importlib.util.module_from_spec(san_spec)
    sys.modules["server.chat.tools.sanitization"] = san_mod
    san_spec.loader.exec_module(san_mod)

    # Stub streaming response functions required by wiki_search / pubmed_search
    streaming_resp_mod = types.ModuleType("server.chat.streaming.response")
    streaming_resp_mod.end_message = MagicMock()
    streaming_resp_mod.status_message = MagicMock()
    sys.modules["server.chat.streaming.response"] = streaming_resp_mod

    # Stub tool helpers required by wiki_search / pubmed_search
    helpers_mod = types.ModuleType("server.chat.tools._helpers")
    helpers_mod.parse_tool_args = MagicMock()
    sys.modules["server.chat.tools._helpers"] = helpers_mod

    # Stub ToolResult
    models_stub = types.ModuleType("server.chat.models")
    models_stub.ToolResult = MagicMock()
    sys.modules["server.chat.models"] = models_stub

    # Load wiki_search.py
    wiki_spec = importlib.util.spec_from_file_location(
        "server.chat.tools.wiki_search",
        Path(__file__).parent / "server/chat/tools/wiki_search.py",
    )
    wiki_mod = importlib.util.module_from_spec(wiki_spec)
    sys.modules["server.chat.tools.wiki_search"] = wiki_mod
    wiki_spec.loader.exec_module(wiki_mod)

    # Load pubmed_search.py
    pubmed_spec = importlib.util.spec_from_file_location(
        "server.chat.tools.pubmed_search",
        Path(__file__).parent / "server/chat/tools/pubmed_search.py",
    )
    pubmed_mod = importlib.util.module_from_spec(pubmed_spec)
    sys.modules["server.chat.tools.pubmed_search"] = pubmed_mod
    pubmed_spec.loader.exec_module(pubmed_mod)

    return san_mod, wiki_mod, pubmed_mod


@pytest.fixture(scope="module")
def search_modules():
    """Load the three modules once and share them across the tests."""
    return _load_search_modules()


def _fake_http_client(json_body):
    """
    Build a stand-in for httpx.AsyncClient that returns `json_body` on any GET.

    Returns (client, get) so tests can inspect what was actually sent via `get`.
    """
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = json_body

    client = AsyncMock()
    get = client.__aenter__.return_value.get
    get.return_value = response
    return client, get


# tests for the sanitization fixes (sanitization.py)


def test_1(search_modules):
    """Passing patient_context scrubs the patient's name from the query."""
    san_mod, _, _ = search_modules
    query = "lower back pain treatment options for Rafa Galvez"
    patient_context = {"name": "Rafa Galvez", "ur_number": "1234567"}

    result = san_mod.sanitize_query_for_external_search(
        query, patient_context=patient_context
    )

    print(f"\n[Test - Patient's Name is Redacted Given `patient_context`]")
    print("-" * 30)
    print(f"result: '{result}'")
    assert "Rafa" not in result
    assert "Galvez" not in result
    assert result == "lower back pain treatment options for"


def test_2(search_modules):
    """sanitize_pubmed_query accepts patient_context and strips the name."""
    san_mod, _, _ = search_modules
    query = "lower back pain treatment options for Rafa Galvez 2026"
    patient_context = {"name": "Rafa Galvez"}

    result = san_mod.sanitize_pubmed_query(query, patient_context=patient_context)

    print(f"\n[Test - PubMed Search with `patient_context`]")
    print("-" * 30)
    print(f"result: '{result}'")
    assert "Rafa" not in result
    assert "Galvez" not in result
    assert "2026" not in result
    assert result == "lower back pain treatment options for"


def test_3(search_modules):
    """A query made up purely of PHI sanitizes to an empty string, not the raw input."""
    san_mod, _, _ = search_modules
    pure_phi_query = "UR 1234567 01/01/2000 0490 20 20 20"

    result = san_mod.sanitize_query_for_external_search(pure_phi_query)

    print(f"\n[Test - Fail-Open Fallback Fix]")
    print("-" * 30)
    print(f"result: '{result}'")
    assert result == ""


def test_4(search_modules):
    """A query containing only the patient's name sanitizes to an empty string."""
    san_mod, _, _ = search_modules
    name_query = "Rafa Galvez"
    patient_context = {"name": "Rafa Galvez"}

    result = san_mod.sanitize_query_for_external_search(
        name_query, patient_context=patient_context
    )

    print(f"\n[Test - Name-Only Fallback Fix]")
    print("-" * 30)
    print(f"result: '{result}'")
    assert result == ""


# outbound network checks (wiki_search & pubmed_search)


def test_5(search_modules):
    """A patient's name inside a longer query is stripped before it goes to Wikipedia."""
    _, wiki_mod, _ = search_modules
    client, get = _fake_http_client({"query": {"search": []}})

    with patch.object(wiki_mod.httpx, "AsyncClient", return_value=client):
        asyncio.run(
            wiki_mod.search_wikipedia(
                "lower back pain treatment options for Rafa Galvez",
                patient_context={"name": "Rafa Galvez"},
            )
        )

    sent_query = get.call_args[1]["params"]["srsearch"]
    print(f"\n[Test - Wikipedia Name Redacted]")
    print("-" * 30)
    print(f"search: '{sent_query}'")
    assert get.called
    assert "Rafa Galvez" not in sent_query
    assert sent_query == "lower back pain treatment options for"


def test_6(search_modules):
    """When the query is purely PHI, nothing is sent to Wikipedia at all."""
    _, wiki_mod, _ = search_modules
    client, get = _fake_http_client({"query": {"search": []}})

    with patch.object(wiki_mod.httpx, "AsyncClient", return_value=client):
        results = asyncio.run(
            wiki_mod.search_wikipedia("UR 1234567 01/01/2000 0490 20 20 20")
        )

    print(f"\n[Test - Sent Wikipedia Query when Pure PHI]")
    print("-" * 30)
    print(f"results: {results}, requests made: {get.call_count}")
    assert results == []
    get.assert_not_called()


def test_7(search_modules):
    """A patient's name and a stray year are stripped before the query goes to PubMed."""
    _, _, pubmed_mod = search_modules
    client, get = _fake_http_client({"esearchresult": {"idlist": []}})

    with patch.object(pubmed_mod.httpx, "AsyncClient", return_value=client):
        asyncio.run(
            pubmed_mod.search_pubmed(
                "lower back pain treatment options for Rafa Galvez 2026",
                patient_context={"name": "Rafa Galvez"},
            )
        )

    sent_term = get.call_args[1]["params"]["term"]
    print(f"\n[Test - PubMed Name Redacted]")
    print("-" * 30)
    print(f"term: '{sent_term}'")
    assert get.called
    assert "Rafa" not in sent_term
    assert "Galvez" not in sent_term
    assert "2026" not in sent_term
    assert sent_term == "lower back pain treatment options for"


def test_8(search_modules):
    """When the query is purely PHI, nothing is sent to PubMed at all."""
    _, _, pubmed_mod = search_modules
    client, get = _fake_http_client({"esearchresult": {"idlist": []}})

    with patch.object(pubmed_mod.httpx, "AsyncClient", return_value=client):
        results = asyncio.run(
            pubmed_mod.search_pubmed("UR 1234567 01/01/2000 0490 20 20 20")
        )

    print(f"\n[Test - Sent PubMed Query when Pure PHI]")
    print("-" * 30)
    print(f"results: {results}, requests made: {get.call_count}")
    assert results == []
    get.assert_not_called()
