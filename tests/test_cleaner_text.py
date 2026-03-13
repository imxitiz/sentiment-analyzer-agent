from agents.cleaner.models import CleaningRuntimeConfig
from agents.services.cleaner_text import clean_document


def test_clean_document_converts_emoji_and_contractions() -> None:
    runtime = CleaningRuntimeConfig(
        remove_punctuation=True,
        lowercase_text=True,
        replace_urls_with_token=True,
    )
    doc = {
        "document_id": "doc_1",
        "content_text": "I can't believe this 😡!!! Visit https://example.com now",
        "content_items": [],
    }

    result = clean_document(doc, runtime)

    assert result.status == "accepted"
    assert "cannot" in result.cleaned_text
    assert "face" in result.cleaned_text
    assert "enraged" in result.cleaned_text or "angry" in result.cleaned_text
    assert "<url>" in result.cleaned_text
    assert result.cleaned_hash is not None


def test_clean_document_extracts_from_html_when_text_missing() -> None:
    runtime = CleaningRuntimeConfig()
    doc = {
        "document_id": "doc_2",
        "raw_html": "<html><body><h1>Big Win</h1><script>x=1</script><p>People are happy 😀</p></body></html>",
        "content_items": [],
    }

    result = clean_document(doc, runtime)

    assert result.status == "accepted"
    assert "big win" in result.cleaned_text
    assert "people are happy" in result.cleaned_text
    assert "script" not in result.cleaned_text


def test_clean_document_marks_too_short() -> None:
    runtime = CleaningRuntimeConfig(min_clean_chars=50)
    doc = {
        "document_id": "doc_3",
        "content_text": "ok",
    }

    result = clean_document(doc, runtime)

    assert result.status == "too_short"
