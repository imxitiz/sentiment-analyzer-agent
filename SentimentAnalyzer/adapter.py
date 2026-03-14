"""Abstract base adapter for all sentiment analysis providers.

Every provider adapter (HuggingFace, dummy, …) must inherit from
``BaseSentimentAdapter`` and implement a small set of abstract methods.  The
base class then provides the **full public API** (sync analyze, async analyze,
batch processing, structured logging, error handling) so individual adapters
stay tiny and consistent.

Contract
--------
    Subclasses **must** implement:
        ``_provider``         – class-level str
        ``_default_model``    – class-level str
        ``_registry_models``  – class-level tuple
        ``_build_model()``    – create the sentiment analysis pipeline

    Everything else (``analyze``, ``analyze_batch``, ``get_score``,
    ``get_score_batch``, logging, error handling) is handled here.

Sentiment Score Convention
--------------------------
    All sentiment scores are continuous values in the range [0.0, 1.0]:
    - 0.0 = very negative
    - 0.5 = neutral
    - 1.0 = very positive

    For models that output discrete labels (e.g., positive/negative/neutral),
    adapters must map them to the continuous scale.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Optional

from Logging import get_logger, context_logger


class SentimentResult:
    """Result of sentiment analysis.

    Attributes
    ----------
    score : float
        Continuous sentiment score in [0.0, 1.0].
        0.0 = very negative, 0.5 = neutral, 1.0 = very positive.
    label : str
        Human-readable sentiment label (e.g., "positive", "negative", "neutral").
    confidence : float
        Model confidence in the prediction, in [0.0, 1.0].
    model : str
        Name of the model used for analysis.
    raw : dict
        Raw model output for debugging.
    """

    def __init__(
        self,
        score: float,
        label: str,
        confidence: float,
        model: str,
        raw: dict[str, Any] | None = None,
    ) -> None:
        self.score = score
        self.label = label
        self.confidence = confidence
        self.model = model
        self.raw = raw or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "score": self.score,
            "label": self.label,
            "confidence": self.confidence,
            "model": self.model,
            "raw": self.raw,
        }

    def __repr__(self) -> str:
        return (
            f"SentimentResult(score={self.score:.3f}, label={self.label!r}, "
            f"confidence={self.confidence:.3f}, model={self.model!r})"
        )


class BaseSentimentAdapter(ABC):
    """Abstract base class every sentiment analyzer adapter must implement.

    Subclasses only need to set three class attributes and implement
    ``_build_model()``.  The rest is inherited.
    """

    # ── Subclass must override these ─────────────────────────────────
    _provider: str = ""  # e.g. "huggingface"
    _default_model: str = ""  # e.g. "distilroberta-base"
    _registry_models: tuple[str, ...] = ()

    def __init__(
        self,
        model: str | None = None,
        *,
        device: str | None = None,
        batch_size: int = 8,
        **kwargs: Any,
    ) -> None:
        self._model = model or self._default_model
        self._device = device
        self._batch_size = batch_size
        self._extra: dict[str, Any] = kwargs
        self._pipeline: Any = None  # Will be set by _build_model()

        # Each adapter instance gets a context-bound logger
        self._log = context_logger(
            f"SentimentAnalyzer.{self._provider}",
            actor=f"{self._provider}_adapter",
            phase="SENTIMENT",
        )

        self._log.info(
            "Initialising %s  model=%s  device=%s  batch_size=%d",
            self.__class__.__name__,
            self._model,
            self._device or "auto",
            self._batch_size,
            action="adapter_init",
            meta={
                "provider": self._provider,
                "model": self._model,
                "device": self._device,
                "batch_size": self._batch_size,
                "extra_keys": list(kwargs.keys()),
            },
        )
        self._build_model()

    # ── Abstract: subclass must implement ─────────────────────────────

    @abstractmethod
    def _build_model(self) -> None:
        """Create ``self._pipeline`` – the sentiment analysis pipeline.

        Must set ``self._pipeline``.  Should raise ``ImportError`` with a
        helpful message if the provider package is missing.
        """
        ...

    @abstractmethod
    def _predict(self, text: str) -> dict[str, Any]:
        """Run sentiment prediction on a single text.

        Returns a dict with at least:
        - "score": float in [0.0, 1.0]
        - "label": str (e.g., "positive", "negative", "neutral")
        - "confidence": float in [0.0, 1.0]
        """
        ...

    @abstractmethod
    def _predict_batch(self, texts: list[str]) -> list[dict[str, Any]]:
        """Run sentiment prediction on a batch of texts.

        Returns a list of dicts, each with:
        - "score": float in [0.0, 1.0]
        - "label": str
        - "confidence": float in [0.0, 1.0]
        """
        ...

    # ── Identity (concrete – derived from class attrs) ────────────────

    @property
    def provider(self) -> str:
        """Canonical provider key."""
        return self._provider

    @property
    def model_name(self) -> str:
        """Currently-selected model name."""
        return self._model

    # ── Core capabilities (concrete) ──────────────────────────────────

    def analyze(self, text: str) -> SentimentResult:
        """Analyze sentiment of a single text.

        Parameters
        ----------
        text : str
            The text to analyze.

        Returns
        -------
        SentimentResult
            Sentiment analysis result with score, label, and confidence.
        """
        self._log.info(
            "analyze called  text_len=%d",
            len(text),
            action="analyze",
            meta={"text_len": len(text)},
        )

        t0 = time.perf_counter()
        try:
            result_dict = self._predict(text)
            elapsed = time.perf_counter() - t0

            result = SentimentResult(
                score=result_dict["score"],
                label=result_dict["label"],
                confidence=result_dict["confidence"],
                model=self._model,
                raw=result_dict.get("raw", {}),
            )

            self._log.success(
                "analyze OK  score=%.3f  label=%s  confidence=%.3f  elapsed=%.3fs",
                result.score,
                result.label,
                result.confidence,
                elapsed,
                action="analyze",
                meta={
                    "score": result.score,
                    "label": result.label,
                    "confidence": result.confidence,
                    "elapsed_s": round(elapsed, 3),
                },
            )
            return result

        except Exception as exc:
            elapsed = time.perf_counter() - t0
            self._log.error(
                "analyze FAILED  error=%s  elapsed=%.3fs",
                exc,
                elapsed,
                action="analyze",
                reason=type(exc).__name__,
                meta={"error": str(exc), "elapsed_s": round(elapsed, 3)},
                exc_info=True,
            )
            raise RuntimeError(
                f"{self.__class__.__name__} analysis failed ({self._model}): {exc}"
            ) from exc

    def analyze_batch(self, texts: list[str]) -> list[SentimentResult]:
        """Analyze sentiment of multiple texts.

        Parameters
        ----------
        texts : list[str]
            List of texts to analyze.

        Returns
        -------
        list[SentimentResult]
            List of sentiment analysis results.
        """
        self._log.info(
            "analyze_batch called  num_texts=%d",
            len(texts),
            action="analyze_batch",
            meta={"num_texts": len(texts)},
        )

        t0 = time.perf_counter()
        try:
            results_dict = self._predict_batch(texts)
            elapsed = time.perf_counter() - t0

            results = [
                SentimentResult(
                    score=r["score"],
                    label=r["label"],
                    confidence=r["confidence"],
                    model=self._model,
                    raw=r.get("raw", {}),
                )
                for r in results_dict
            ]

            self._log.success(
                "analyze_batch OK  num_results=%d  elapsed=%.3fs",
                len(results),
                elapsed,
                action="analyze_batch",
                meta={
                    "num_results": len(results),
                    "elapsed_s": round(elapsed, 3),
                },
            )
            return results

        except Exception as exc:
            elapsed = time.perf_counter() - t0
            self._log.error(
                "analyze_batch FAILED  error=%s  elapsed=%.3fs",
                exc,
                elapsed,
                action="analyze_batch",
                reason=type(exc).__name__,
                meta={"error": str(exc), "elapsed_s": round(elapsed, 3)},
                exc_info=True,
            )
            raise RuntimeError(
                f"{self.__class__.__name__} batch analysis failed ({self._model}): {exc}"
            ) from exc

    def get_score(self, text: str) -> float:
        """Get sentiment score only (0→1 continuous).

        Parameters
        ----------
        text : str
            The text to analyze.

        Returns
        -------
        float
            Sentiment score in [0.0, 1.0].
        """
        return self.analyze(text).score

    def get_score_batch(self, texts: list[str]) -> list[float]:
        """Get sentiment scores only (0→1 continuous) for multiple texts.

        Parameters
        ----------
        texts : list[str]
            List of texts to analyze.

        Returns
        -------
        list[float]
            List of sentiment scores in [0.0, 1.0].
        """
        return [r.score for r in self.analyze_batch(texts)]

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} provider={self._provider!r} "
            f"model={self._model!r}>"
        )
