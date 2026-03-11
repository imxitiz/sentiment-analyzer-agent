from __future__ import annotations

import json


def test_duckduckgo_search_fallback(monkeypatch):
    """Ensure the DDG branch returns a well-formed demo response when the
    underlying tool raises an error.

    We monkeypatch the LangChain community wrapper to throw so that the code
    takes the demo path.  The returned JSON must contain the expected keys and
    the ``engine`` field should equal ``"duckduckgo"``.
    """

    # create a dummy class that blows up during invocation
    class BrokenSearch:
        def __init__(self, *args, **kwargs):
            pass

        def invoke(self, query: str):
            raise RuntimeError("simulated failure")

    # ensure the import inside search_engine_snippets will succeed but the call fails
    try:
        import langchain_community.tools
    except ImportError:  # if the package isn't installed simply skip network test
        pass
    else:
        monkeypatch.setattr(
            "langchain_community.tools.DuckDuckGoSearchRun",
            BrokenSearch,
            raising=False,
        )

    from agents.tools.search import search_engine_snippets

    # the decorator wraps the callable; ``.func`` gives us the original
    tool_fn = getattr(search_engine_snippets, "func", search_engine_snippets)
    assert callable(tool_fn)

    resp_text = tool_fn("my topic", engine="duckduckgo", max_results=2)
    resp = json.loads(str(resp_text))

    assert resp.get("engine") == "duckduckgo"
    assert resp.get("query") == "my topic"
    assert resp.get("demo") is True
    assert resp.get("count", 0) >= 1
    assert isinstance(resp.get("results"), list)


def test_google_search_engine_restriction():
    """Verify the error case for unsupported engines."""
    from agents.tools.search import search_engine_snippets

    tool_fn = getattr(search_engine_snippets, "func", search_engine_snippets)
    assert callable(tool_fn)

    resp = json.loads(str(tool_fn("foo", engine="bing")))
    assert resp.get("ok") is False
    assert "Unsupported engine" in resp.get("error", "")
