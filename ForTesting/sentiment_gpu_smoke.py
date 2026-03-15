"""Quick smoke test for HuggingFace sentiment analysis with device checks.

Usage:
    uv run python ForTesting/sentiment_gpu_smoke.py
    uv run python ForTesting/sentiment_gpu_smoke.py --device cuda --batch-size 16
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Logging import get_logger  # noqa: E402
from SentimentAnalyzer import get_sentiment_analyzer  # noqa: E402

logger = get_logger("sentiment_gpu_smoke")


def _detect_torch() -> dict[str, Any]:
    try:
        import torch  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        return {"available": False, "error": str(exc)}

    info: dict[str, Any] = {
        "available": True,
        "version": getattr(torch, "__version__", "unknown"),
    }
    try:
        cuda = getattr(torch, "cuda", None)
        if cuda is None:
            info["cuda_available"] = False
            info["cuda_device_count"] = 0
        else:
            info["cuda_available"] = bool(cuda.is_available())
            info["cuda_device_count"] = int(cuda.device_count())
            if info["cuda_available"] and info["cuda_device_count"] > 0:
                info["cuda_device_name"] = cuda.get_device_name(0)
    except Exception as exc:  # pragma: no cover - optional path
        info["cuda_error"] = str(exc)

    try:
        info["mps_available"] = bool(
            hasattr(torch, "backends")
            and hasattr(torch.backends, "mps")
            and torch.backends.mps.is_available()
        )
    except Exception as exc:  # pragma: no cover - optional path
        info["mps_error"] = str(exc)

    return info


def _resolve_device(requested: str, torch_info: dict[str, Any]) -> str | None:
    if requested == "auto":
        if torch_info.get("cuda_available"):
            return "cuda"
        if torch_info.get("mps_available"):
            return "mps"
        return None
    if requested == "cpu":
        return "cpu"
    if requested == "cuda":
        return "cuda"
    if requested == "mps":
        return "mps"
    return None


def _pipeline_device(analyzer: Any) -> str | None:
    pipeline = getattr(analyzer, "_pipeline", None)
    model = getattr(pipeline, "model", None)
    device = getattr(model, "device", None)
    if device is None:
        return None
    return str(device)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sentiment GPU smoke test")
    parser.add_argument(
        "--model",
        default="cardiffnlp/twitter-roberta-base-sentiment-latest",
        help="HuggingFace model name",
    )
    parser.add_argument(
        "--device",
        default="auto",
        choices=("auto", "cpu", "cuda", "mps"),
        help="Device preference (auto/cpu/cuda/mps)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="Batch size for pipeline inference",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=3,
        help="Number of batch repeats for timing",
    )
    args = parser.parse_args()

    torch_info = _detect_torch()
    logger.info("Torch info: %s", torch_info)

    if not torch_info.get("available"):
        logger.error(
            "PyTorch not available; install transformers + torch before running."
        )
        return 1

    device = _resolve_device(args.device, torch_info)
    logger.info("Requested device=%s resolved=%s", args.device, device or "auto")

    try:
        analyzer = get_sentiment_analyzer(
            provider="huggingface",
            model=args.model,
            device=device,
            batch_size=args.batch_size,
        )
    except Exception as exc:
        logger.error("Failed to create sentiment analyzer: %s", exc)
        return 1

    # Warm-up
    warmup_text = "I love how responsive this system feels today."
    warmup = analyzer.analyze(warmup_text)
    logger.info(
        "Warmup result: score=%.3f label=%s confidence=%.3f",
        warmup.score,
        warmup.label,
        warmup.confidence,
    )

    # Batch test
    texts = [
        "This is fantastic!",
        "I'm not sure how I feel about this.",
        "Terrible experience, would not recommend.",
        "Pretty good overall.",
        "Absolutely loved it.",
        "This was a waste of time.",
        "Neutral statement about the topic.",
        "Could be better, could be worse.",
    ]
    batched = texts * max(1, args.batch_size // max(1, len(texts)))
    batched = batched[: max(1, args.batch_size)]

    results = []
    start = time.perf_counter()
    for _ in range(max(1, args.repeats)):
        results = analyzer.analyze_batch(batched)
    elapsed = time.perf_counter() - start
    total = len(batched) * max(1, args.repeats)
    logger.info(
        "Batch run complete: total=%d elapsed=%.3fs throughput=%.2f items/s",
        total,
        elapsed,
        total / elapsed if elapsed > 0 else 0.0,
    )

    print("Sample batch results:")
    print(f"{'Text':<50} {'Score':>6} {'Label':>10} {'Confidence':>12}")
    for text, result in zip(batched, results):
        logger.info(
            "  → Text: %.50s Score: %.3f Label: %s Confidence: %.3f",
            text,
            result.score,
            result.label,
            result.confidence,
        )

    if results:
        logger.info(
            "Sample result: score=%.3f label=%s confidence=%.3f",
            results[0].score,
            results[0].label,
            results[0].confidence,
        )

    actual_device = _pipeline_device(analyzer)
    if actual_device:
        logger.info("Pipeline model device: %s", actual_device)

    try:
        import torch  # type: ignore

        if actual_device and "cuda" in actual_device:
            logger.info(
                "CUDA memory allocated: %.2f MB",
                torch.cuda.memory_allocated() / (1024 * 1024),
            )
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
