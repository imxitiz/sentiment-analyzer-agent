"""Adaptive text-cleaning utilities for phase-4 preprocessing."""

from __future__ import annotations

import hashlib
import html
import importlib
import re
import string
from dataclasses import asdict, replace
from typing import Any, cast

from bs4 import BeautifulSoup

from agents.cleaner.models import CleanerPlan, CleanerResult, CleaningRuntimeConfig

_URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_MENTION_PATTERN = re.compile(r"(?<!\w)@[A-Za-z0-9_]{2,64}")
_HASHTAG_PATTERN = re.compile(r"#([A-Za-z0-9_]+)")
_WHITESPACE_PATTERN = re.compile(r"\s+")
_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
_WORD_PATTERN = re.compile(r"\b\w+\b", re.UNICODE)

_CONTRACTION_MAP = {
    "can't": "cannot",
    "won't": "will not",
    "n't": " not",
    "'re": " are",
    "'s": " is",
    "'d": " would",
    "'ll": " will",
    "'t": " not",
    "'ve": " have",
    "'m": " am",
}


def _hash_text(value: str) -> str | None:
    normalized = value.strip()
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _safe_import(module: str) -> Any | None:
    try:
        return importlib.import_module(module)
    except Exception:
        return None


def _strip_html(value: str) -> str:
    if not value:
        return ""
    soup = BeautifulSoup(value, "lxml")
    for bad in soup(["script", "style", "noscript", "svg", "canvas", "iframe"]):
        bad.decompose()
    return soup.get_text(" ", strip=True)


def _extract_via_trafilatura(raw_html: str) -> str:
    trafilatura = _safe_import("trafilatura")
    if trafilatura is None:
        return ""
    extract = getattr(trafilatura, "extract", None)
    if not callable(extract):
        return ""
    try:
        extracted = extract(
            raw_html,
            include_comments=True,
            favor_precision=False,
            favor_recall=True,
            output_format="txt",
        )
        return str(extracted or "").strip()
    except Exception:
        return ""


def _extract_via_readability(raw_html: str) -> str:
    readability = _safe_import("readability")
    if readability is None:
        return ""
    document_cls = getattr(readability, "Document", None)
    if document_cls is None:
        return ""
    try:
        summary_html = document_cls(raw_html).summary()
        return _strip_html(str(summary_html or ""))
    except Exception:
        return ""


def _normalize_markdown(value: str) -> str:
    text = value
    text = re.sub(r"`{1,3}[^`]*`{1,3}", " ", text)
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r" \1 ", text)
    text = re.sub(r"[*_~#>-]", " ", text)
    return _WHITESPACE_PATTERN.sub(" ", text).strip()


def _fix_unicode(value: str) -> str:
    if not value:
        return ""
    ftfy_module = _safe_import("ftfy")
    if ftfy_module is None:
        return value
    fixer = getattr(ftfy_module, "fix_text", None)
    if not callable(fixer):
        return value
    try:
        return str(fixer(value))
    except Exception:
        return value


def _demojize_text(value: str) -> str:
    if not value:
        return ""
    emoji_module = _safe_import("emoji")
    if emoji_module is None:
        return value
    demojize_fn = getattr(emoji_module, "demojize", None)
    if not callable(demojize_fn):
        return value
    try:
        output = str(demojize_fn(value, delimiters=(" ", " ")))
        output = output.replace("_", " ")
        return _WHITESPACE_PATTERN.sub(" ", output).strip()
    except Exception:
        return value


def _expand_contractions(value: str) -> str:
    if not value:
        return ""
    contractions_module = _safe_import("contractions")
    if contractions_module is not None:
        fixer = getattr(contractions_module, "fix", None)
        if callable(fixer):
            try:
                return str(fixer(value))
            except Exception:
                pass

    out = value
    for old, new in _CONTRACTION_MAP.items():
        out = re.sub(re.escape(old), new, out, flags=re.IGNORECASE)
    return out


def _collect_backend_candidates(
    document: dict[str, Any], runtime: CleaningRuntimeConfig
) -> dict[str, str]:
    candidates: dict[str, str] = {}
    raw_html = str(document.get("raw_html") or "").strip()

    if "content_fields" in runtime.extraction_backends:
        chunks: list[str] = []
        for key in ("title", "description", "content_text", "raw_text"):
            value = document.get(key)
            if isinstance(value, str) and value.strip():
                chunks.append(value.strip())

        markdown = document.get("markdown")
        if isinstance(markdown, str) and markdown.strip():
            chunks.append(_normalize_markdown(markdown))

        for item in document.get("content_items") or []:
            if not isinstance(item, dict):
                continue
            title = item.get("title")
            text = item.get("text")
            if isinstance(title, str) and title.strip():
                chunks.append(title.strip())
            if isinstance(text, str) and text.strip():
                chunks.append(
                    _strip_html(text)
                    if _HTML_TAG_PATTERN.search(text)
                    else text.strip()
                )

        candidates["content_fields"] = _WHITESPACE_PATTERN.sub(
            " ",
            "\n".join(chunks),
        ).strip()

    if raw_html and "trafilatura" in runtime.extraction_backends:
        candidates["trafilatura"] = _extract_via_trafilatura(raw_html)

    if raw_html and "readability" in runtime.extraction_backends:
        candidates["readability"] = _extract_via_readability(raw_html)

    if raw_html and "bs4" in runtime.extraction_backends:
        candidates["bs4"] = _strip_html(raw_html)

    return {name: text for name, text in candidates.items() if text.strip()}


def _raw_feature_scores(text: str) -> dict[str, float]:
    if not text:
        return {
            "char_count": 0.0,
            "token_count": 0.0,
            "alpha_ratio": 0.0,
            "url_ratio": 1.0,
            "symbol_ratio": 1.0,
            "unique_token_ratio": 0.0,
            "quality_score": 0.0,
        }

    chars = len(text)
    tokens = _WORD_PATTERN.findall(text)
    token_count = len(tokens)
    alpha_count = sum(1 for c in text if c.isalpha())
    url_like_chars = sum(len(match.group(0)) for match in _URL_PATTERN.finditer(text))
    symbol_count = sum(1 for c in text if not c.isalnum() and not c.isspace())
    unique_ratio = len({tok.lower() for tok in tokens}) / max(1, token_count)
    alpha_ratio = alpha_count / max(1, chars)
    url_ratio = url_like_chars / max(1, chars)
    symbol_ratio = symbol_count / max(1, chars)

    quality_score = (
        min(1.0, token_count / 140.0) * 0.25
        + alpha_ratio * 0.4
        + unique_ratio * 0.2
        + max(0.0, 1.0 - url_ratio) * 0.1
        + max(0.0, 1.0 - symbol_ratio) * 0.05
    )

    return {
        "char_count": float(chars),
        "token_count": float(token_count),
        "alpha_ratio": float(alpha_ratio),
        "url_ratio": float(url_ratio),
        "symbol_ratio": float(symbol_ratio),
        "unique_token_ratio": float(unique_ratio),
        "quality_score": float(max(0.0, min(1.0, quality_score))),
    }


def _pick_best_source(candidates: dict[str, str]) -> tuple[str, str, dict[str, float]]:
    best_backend = ""
    best_text = ""
    best_scores: dict[str, float] = {}
    best_quality = -1.0
    for backend, text in candidates.items():
        scores = _raw_feature_scores(text)
        quality = scores.get("quality_score", 0.0)
        if quality > best_quality:
            best_quality = quality
            best_backend = backend
            best_text = text
            best_scores = scores
    return best_backend, best_text, best_scores


def _apply_plan_overrides(
    runtime: CleaningRuntimeConfig, plan: CleanerPlan | None
) -> CleaningRuntimeConfig:
    if plan is None:
        return runtime

    updates: dict[str, Any] = {}
    for field in (
        "remove_punctuation",
        "lowercase_text",
        "replace_urls_with_token",
        "replace_mentions_with_token",
        "min_clean_chars",
        "max_clean_chars",
        "min_alpha_ratio",
        "max_url_ratio",
        "max_symbol_ratio",
        "reject_non_preferred_languages",
        "enable_fuzzy_dedupe",
        "fuzzy_dedupe_threshold",
    ):
        value = getattr(plan, field)
        if value is not None:
            updates[field] = value

    if plan.preferred_languages:
        updates["preferred_languages"] = tuple(plan.preferred_languages)

    if plan.custom_noise_patterns:
        updates["custom_noise_patterns"] = tuple(plan.custom_noise_patterns)

    return replace(runtime, **updates)


def _apply_custom_noise_filters(
    text: str, runtime: CleaningRuntimeConfig, plan: CleanerPlan | None
) -> str:
    result = text
    patterns = list(runtime.custom_noise_patterns)
    if plan is not None:
        patterns.extend(plan.extra_remove_regexes)

    for pattern in patterns:
        try:
            result = re.sub(pattern, " ", result, flags=re.IGNORECASE)
        except re.error:
            continue

    if plan is not None:
        for old, new in plan.replacement_rules.items():
            if not old:
                continue
            result = result.replace(old, new)

    return _WHITESPACE_PATTERN.sub(" ", result).strip()


def _normalize_text(
    value: str, runtime: CleaningRuntimeConfig, plan: CleanerPlan | None
) -> str:
    text = html.unescape(value)
    text = _fix_unicode(text)
    text = _demojize_text(text)
    text = _expand_contractions(text)

    if runtime.replace_mentions_with_token:
        text = _MENTION_PATTERN.sub(" @user ", text)
    text = _HASHTAG_PATTERN.sub(r" \1 ", text)

    if runtime.replace_urls_with_token:
        text = _URL_PATTERN.sub(" <url> ", text)

    text = _apply_custom_noise_filters(text, runtime, plan)
    text = _WHITESPACE_PATTERN.sub(" ", text).strip()

    if runtime.remove_punctuation:
        punct = string.punctuation.replace("<", "").replace(">", "")
        text = text.translate(str.maketrans({ord(char): " " for char in punct}))

    text = _WHITESPACE_PATTERN.sub(" ", text).strip()

    if runtime.lowercase_text:
        text = text.lower()

    return text


def _detect_language(text: str) -> tuple[str | None, list[tuple[str, float]]]:
    if not text.strip():
        return None, []
    langdetect = _safe_import("langdetect")
    if langdetect is None:
        return None, []

    detector_factory = getattr(langdetect, "DetectorFactory", None)
    detect_langs = getattr(langdetect, "detect_langs", None)
    if detector_factory is not None:
        try:
            detector_factory.seed = 0
        except Exception:
            pass
    if not callable(detect_langs):
        return None, []

    try:
        langs_obj = detect_langs(text[:4000])
    except Exception:
        return None, []

    if not isinstance(langs_obj, list):
        return None, []
    langs = cast(list[Any], langs_obj)

    parsed: list[tuple[str, float]] = []
    for item in langs:
        language = str(getattr(item, "lang", "") or "").strip().lower()
        prob = float(getattr(item, "prob", 0.0) or 0.0)
        if language:
            parsed.append((language, prob))
    best = parsed[0][0] if parsed else None
    return best, parsed


def clean_document(
    document: dict[str, Any],
    runtime: CleaningRuntimeConfig,
    *,
    plan: CleanerPlan | None = None,
) -> CleanerResult:
    """Clean a raw MongoDB document into sentiment-ready text."""
    applied_runtime = _apply_plan_overrides(runtime, plan)
    candidates = _collect_backend_candidates(document, applied_runtime)
    if not candidates:
        return CleanerResult(
            status="failed",
            cleaned_text="",
            sentiment_text="",
            cleaned_hash=None,
            source_text="",
            reason="No extractable text found in document payload.",
            quality_flags=["empty_source"],
            metrics={"source_chars": 0, "clean_chars": 0},
            features={"source_backend": "none"},
        )

    source_backend, source_text, source_scores = _pick_best_source(candidates)
    cleaned = _normalize_text(source_text, applied_runtime, plan)
    cleaned_scores = _raw_feature_scores(cleaned)
    clean_chars = int(cleaned_scores.get("char_count", 0.0))
    source_chars = int(source_scores.get("char_count", 0.0))

    language, language_probs = _detect_language(cleaned)
    quality_flags: list[str] = []

    if clean_chars < applied_runtime.min_clean_chars:
        quality_flags.append("too_short")
        return CleanerResult(
            status="too_short",
            cleaned_text=cleaned,
            sentiment_text=cleaned,
            cleaned_hash=_hash_text(cleaned),
            source_text=source_text,
            reason="Cleaned text is below minimum length threshold.",
            quality_flags=quality_flags,
            metrics={"source_chars": source_chars, "clean_chars": clean_chars},
            features={
                "source_backend": source_backend,
                "source_scores": source_scores,
                "cleaned_scores": cleaned_scores,
                "language": language,
                "language_probs": language_probs,
            },
        )

    if clean_chars > applied_runtime.max_clean_chars:
        cleaned = cleaned[: applied_runtime.max_clean_chars].strip()
        cleaned_scores = _raw_feature_scores(cleaned)
        clean_chars = int(cleaned_scores.get("char_count", 0.0))
        quality_flags.append("truncated")

    alpha_ratio = float(cleaned_scores.get("alpha_ratio", 0.0))
    url_ratio = float(cleaned_scores.get("url_ratio", 1.0))
    symbol_ratio = float(cleaned_scores.get("symbol_ratio", 1.0))

    if alpha_ratio < applied_runtime.min_alpha_ratio:
        quality_flags.append("low_alpha_ratio")
    if url_ratio > applied_runtime.max_url_ratio:
        quality_flags.append("high_url_ratio")
    if symbol_ratio > applied_runtime.max_symbol_ratio:
        quality_flags.append("high_symbol_ratio")

    if applied_runtime.reject_non_preferred_languages and language is not None:
        preferred = {lang.lower() for lang in applied_runtime.preferred_languages}
        if language.lower() not in preferred:
            quality_flags.append("language_filtered")

    if any(
        flag
        in {
            "low_alpha_ratio",
            "high_url_ratio",
            "high_symbol_ratio",
            "language_filtered",
        }
        for flag in quality_flags
    ):
        return CleanerResult(
            status="failed",
            cleaned_text=cleaned,
            sentiment_text=cleaned,
            cleaned_hash=_hash_text(cleaned),
            source_text=source_text,
            reason="Quality gates rejected cleaned text.",
            quality_flags=quality_flags,
            metrics={"source_chars": source_chars, "clean_chars": clean_chars},
            features={
                "source_backend": source_backend,
                "source_scores": source_scores,
                "cleaned_scores": cleaned_scores,
                "language": language,
                "language_probs": language_probs,
            },
        )

    return CleanerResult(
        status="accepted",
        cleaned_text=cleaned,
        sentiment_text=cleaned,
        cleaned_hash=_hash_text(cleaned),
        source_text=source_text,
        reason="Adaptive deterministic cleaning succeeded.",
        quality_flags=quality_flags,
        metrics={"source_chars": source_chars, "clean_chars": clean_chars},
        features={
            "source_backend": source_backend,
            "source_scores": source_scores,
            "cleaned_scores": cleaned_scores,
            "language": language,
            "language_probs": language_probs,
        },
    )


def describe_runtime(runtime: CleaningRuntimeConfig) -> dict[str, Any]:
    """Serializable runtime metadata."""
    return asdict(runtime)
