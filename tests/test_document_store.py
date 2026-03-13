from agents.scraper.models import ScrapedContent, ScrapeTarget
from agents.services.document_store import _build_document_payload, _stable_document_id


def test_stable_document_id_uses_normalized_url() -> None:
    url = "https://example.com/post/42"
    assert _stable_document_id(url) == _stable_document_id(url)
    assert _stable_document_id(url).startswith("doc_")


def test_document_payload_normalizes_child_items_and_references() -> None:
    target = ScrapeTarget(
        discovered_link_id=11,
        unique_id="topic-a-1",
        normalized_url="https://example.com/post/42",
        url="https://example.com/post/42?utm=test",
        topic="topic-a",
        domain="example.com",
        platform="web",
        title="Example title",
        description="Example description",
        source_name="serper",
    )
    document = ScrapedContent(
        fetch_backend="generic_http",
        normalized_url=target.normalized_url,
        final_url="https://example.com/post/42",
        platform="web",
        domain="example.com",
        title="Example title",
        description="Example description",
        author="alice",
        content_text="Main body",
        excerpt="Main body",
        raw_text="Main body",
        authors=[{"name": "alice"}],
        references=[{"kind": "canonical", "url": "https://example.com/post/42"}],
        content_items=[
            {
                "kind": "comment",
                "text": "Nested comment",
                "author": "bob",
                "source_url": "https://example.com/post/42#comment-1",
                "metadata": {"score": 7},
            }
        ],
        metadata={"lang": "en"},
    )

    payload = _build_document_payload(
        topic="topic-a",
        topic_slug="topic-a",
        run_id="run-1",
        target=target,
        document=document,
        document_id=_stable_document_id(target.normalized_url),
    )

    assert payload["document_id"] == _stable_document_id(target.normalized_url)
    assert payload["target_id"] == "topic-a-1"
    assert payload["authors"][0]["name"] == "alice"
    assert payload["content_items"][0]["kind"] == "comment"
    assert payload["content_items"][0]["metrics"]["score"] == 7
    assert payload["references"][0]["url"] == "https://example.com/post/42"
    assert payload["topic_refs"]["topic-a"]["target_id"] == "topic-a-1"
