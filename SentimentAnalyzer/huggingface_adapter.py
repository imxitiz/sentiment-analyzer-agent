"""HuggingFace Transformers adapter for sentiment analysis.

This adapter uses HuggingFace's ``transformers`` pipeline for sentiment
classification.  It supports multiple sentiment models and provides
continuous scores (0→1) for all outputs.

Usage
-----
    from SentimentAnalyzer import get_sentiment_analyzer

    # Default model (cardiffnlp/twitter-roberta-base-sentiment-latest)
    analyzer = get_sentiment_analyzer()
    result = analyzer.analyze("I love this product!")
    print(f"Score: {result.score:.3f}, Label: {result.label}")

    # Twitter-optimized model
    analyzer = get_sentiment_analyzer(model="cardiffnlp/twitter-roberta-base-sentiment-latest")
    result = analyzer.analyze("This is amazing! 🎉")

    # Multilingual model
    analyzer = get_sentiment_analyzer(model="nlptown/bert-base-multilingual-uncased-sentiment")
    result = analyzer.analyze("This is great!")  # Works in multiple languages

Requirements
------------
    pip install "transformers>=4.30.0" "torch>=2.6.0"

    Or install via project dependencies:
    uv sync
"""

from __future__ import annotations

from typing import Any, cast

from .adapter import BaseSentimentAdapter


class HuggingFaceAdapter(BaseSentimentAdapter):
    """HuggingFace Transformers adapter for sentiment analysis.

    This adapter uses HuggingFace's pipeline API for sentiment classification.
    It automatically handles model loading, tokenization, and prediction.

    Parameters
    ----------
    model : str, optional
        HuggingFace model name. Defaults to
        "cardiffnlp/twitter-roberta-base-sentiment-latest".
    device : str, optional
        Device to use ("cpu", "cuda", "mps"). Defaults to auto-detection.
    batch_size : int
        Batch size for batch predictions. Defaults to 8.
    """

    _provider = "huggingface"
    _default_model = "cardiffnlp/twitter-roberta-base-sentiment-latest"
    _registry_models = (
        "cardiffnlp/twitter-roberta-base-sentiment-latest",
        "distilbert-base-uncased-finetuned-sst-2-english",
        "nlptown/bert-base-multilingual-uncased-sentiment",
    )

    def __init__(
        self,
        model: str | None = None,
        *,
        device: str | None = None,
        batch_size: int = 8,
        **kwargs: Any,
    ) -> None:
        self._pipeline = None
        super().__init__(model=model, device=device, batch_size=batch_size, **kwargs)

    def _build_model(self) -> None:
        """Create the HuggingFace sentiment analysis pipeline."""
        try:
            from transformers import pipeline
            import torch
        except ImportError as exc:
            raise ImportError(
                "HuggingFace transformers is required for sentiment analysis. "
                "Install it with: pip install transformers torch "
                "Or via project dependencies: uv sync"
            ) from exc

        torch_any = cast(Any, torch)

        # Auto-detect device if not specified
        if self._device is None:
            if getattr(torch_any, "cuda", None) and torch_any.cuda.is_available():
                self._device = "cuda"
            elif (
                getattr(torch_any, "backends", None)
                and getattr(torch_any.backends, "mps", None)
                and torch_any.backends.mps.is_available()
            ):
                self._device = "mps"
            else:
                self._device = "cpu"

        self._log.info(
            "Loading HuggingFace model  model=%s  device=%s",
            self._model,
            self._device,
            action="build_model",
            meta={"model": self._model, "device": self._device},
        )

        device_arg: Any
        if isinstance(self._device, str):
            if self._device in {"", "auto"}:
                device_arg = None
            elif self._device == "cpu":
                device_arg = -1
            elif self._device.startswith("cuda") or self._device == "mps":
                try:
                    device_arg = torch_any.device(self._device)
                except Exception:
                    device_arg = 0
            else:
                device_arg = self._device
        else:
            device_arg = self._device

        try:
            self._pipeline = pipeline(
                "text-classification",
                model=self._model,
                device=device_arg,
                **self._extra,
            )
            self._log.success(
                "HuggingFace model loaded successfully  model=%s",
                self._model,
                action="build_model",
                meta={"model": self._model},
            )
        except Exception as exc:
            self._log.error(
                "Failed to load HuggingFace model  model=%s  error=%s",
                self._model,
                exc,
                action="build_model",
                reason=type(exc).__name__,
                meta={"model": self._model, "error": str(exc)},
                exc_info=True,
            )
            raise RuntimeError(
                f"Failed to load HuggingFace model {self._model}: {exc}"
            ) from exc

    def _predict(self, text: str) -> dict[str, Any]:
        """Run sentiment prediction on a single text.

        Parameters
        ----------
        text : str
            The text to analyze.

        Returns
        -------
        dict[str, Any]
            Prediction result with score, label, and confidence.
        """
        if self._pipeline is None:
            raise RuntimeError("Pipeline not initialized. Call _build_model() first.")

        # Run prediction
        results = self._pipeline(text)
        result = self._select_result(results)

        # Extract label and score
        label = result.get("label", "unknown")
        raw_score = result.get("score", 0.0)

        # Normalize score to [0.0, 1.0]
        score = self._normalize_score(label, raw_score)

        # Calculate confidence (raw_score is already confidence for most models)
        confidence = raw_score

        return {
            "score": score,
            "label": label,
            "confidence": confidence,
            "raw": result,
        }

    def _predict_batch(self, texts: list[str]) -> list[dict[str, Any]]:
        """Run sentiment prediction on a batch of texts.

        Parameters
        ----------
        texts : list[str]
            List of texts to analyze.

        Returns
        -------
        list[dict[str, Any]]
            List of prediction results.
        """
        if self._pipeline is None:
            raise RuntimeError("Pipeline not initialized. Call _build_model() first.")

        # Run batch prediction
        results = self._pipeline(texts, batch_size=self._batch_size)

        # Process results
        processed = []
        for result in results:
            selected = self._select_result(result)
            label = selected.get("label", "unknown")
            raw_score = selected.get("score", 0.0)

            # Normalize score to [0.0, 1.0]
            score = self._normalize_score(label, raw_score)

            # Calculate confidence
            confidence = raw_score

            processed.append(
                {
                    "score": score,
                    "label": label,
                    "confidence": confidence,
                    "raw": selected,
                }
            )

        return processed

    def _normalize_score(self, label: str, raw_score: float) -> float:
        """Normalize sentiment score to [0.0, 1.0].

        For models that output discrete labels (e.g., positive/negative/neutral),
        we map them to the continuous scale:
        - negative → 0.0
        - neutral → 0.5
        - positive → 1.0

        For star-based models (1-5 stars), we normalize:
        - 1 star → 0.0
        - 3 stars → 0.5
        - 5 stars → 1.0

        For models that already output continuous scores, we use them directly.

        Parameters
        ----------
        label : str
            Predicted label.
        raw_score : float
            Raw score from the model.

        Returns
        -------
        float
            Normalized score in [0.0, 1.0].
        """
        label_lower = label.lower()

        # Handle star-based models (1-5 stars)
        if "star" in label_lower:
            # Extract star count (e.g., "5 stars" → 5)
            try:
                stars = int(label_lower.split()[0])
                # Normalize: 1 star → 0.0, 3 stars → 0.5, 5 stars → 1.0
                return (stars - 1) / 4.0
            except (ValueError, IndexError):
                pass

        # Handle discrete labels (positive/negative/neutral)
        if "positive" in label_lower:
            return 1.0
        elif "negative" in label_lower:
            return 0.0
        elif "neutral" in label_lower:
            return 0.5

        # For models that already output continuous scores, use raw_score
        # Some models output scores in [0.0, 1.0] directly
        if 0.0 <= raw_score <= 1.0:
            return raw_score

        # Fallback: assume raw_score is in [0.0, 1.0]
        return max(0.0, min(1.0, raw_score))

    @staticmethod
    def _select_result(payload: Any) -> dict[str, Any]:
        """Normalize pipeline output into a single result dict."""
        if isinstance(payload, list):
            if not payload:
                return {"label": "neutral", "score": 0.5}
            if all(isinstance(item, dict) for item in payload):
                return max(payload, key=lambda item: item.get("score", 0.0))
            return {"label": "neutral", "score": 0.5}
        if isinstance(payload, dict):
            return payload
        return {"label": "neutral", "score": 0.5}
