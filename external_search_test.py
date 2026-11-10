import asyncio
import importlib.util
from pathlib import Path
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _load_search_modules():
    """
    Import `wiki_search` and `pubmed_search` without booting the whole app.

    A normal import would run every __init__.py on the way down (server/,
    server/chat/, ...), which pulls in the real application. So instead we
    fake those packages and load just the files we want to test, with their
    heavier dependencies swapped for mocks.

    Returns (`wiki_mod`, `pubmed_mod`).
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
    san_spec.loader.exec_module(san_mod)
    sys.modules["server.chat.tools.sanitization"] = san_mod

    # Stub streaming response functions required by wiki_search / pubmed_search
    streaming_resp_mod = types.ModuleType("server.chat.streaming.response")
    streaming_resp_mod.end_message = MagicMock()
    streaming_resp_mod.status_message = MagicMock()
    sys.modules["server.chat.streaming.response"] = streaming_resp_mod

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

    return wiki_mod, pubmed_mod


@pytest.fixture(scope="module")
def search_modules():
    """Load the two search modules once and share them across the tests."""
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


def test_wikipedia_search_leaks_patient_name(search_modules):
    """A patient's name inside a longer query goes out to Wikipedia untouched."""
    wiki_mod, _ = search_modules
    client, get = _fake_http_client({"query": {"search": []}})

    with patch.object(wiki_mod.httpx, "AsyncClient", return_value=client):
        asyncio.run(
            wiki_mod.search_wikipedia("lower back pain treatment for Rafa Galvez")
        )

    sent_query = get.call_args[1]["params"]["srsearch"]
    print(f"\nWikipedia query sent: '{sent_query}'")
    assert "Rafa Galvez" in sent_query


def test_wikipedia_fallback_leaks_raw_phi(search_modules):
    """When sanitization leaves nothing usable, the raw input is sent as-is."""
    wiki_mod, _ = search_modules
    client, get = _fake_http_client({"query": {"search": []}})

    with patch.object(wiki_mod.httpx, "AsyncClient", return_value=client):
        asyncio.run(wiki_mod.search_wikipedia("UR 1234567 14/05/1978"))

    sent_query = get.call_args[1]["params"]["srsearch"]
    print(f"\nWikipedia fallback query sent: '{sent_query}'")
    assert sent_query == "UR 1234567 14/05/1978"


def test_pubmed_search_leaks_patient_name(search_modules):
    """Same name leak as above, but through the PubMed search path."""
    _, pubmed_mod = search_modules
    client, get = _fake_http_client({"esearchresult": {"idlist": []}})

    with patch.object(pubmed_mod.httpx, "AsyncClient", return_value=client):
        asyncio.run(
            pubmed_mod.search_pubmed("lower back pain treatment for Rafa Galvez 2024")
        )

    sent_term = get.call_args[1]["params"]["term"]
    print(f"\nPubMed term sent: '{sent_term}'")
    assert "Rafa Galvez" in sent_term
