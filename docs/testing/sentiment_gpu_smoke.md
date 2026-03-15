# Sentiment GPU Smoke Test (2026-03-15)

## Goal

Verify HuggingFace sentiment analysis runs on GPU end-to-end, confirm device selection, and capture any install/runtime blockers.

## Environment

- Date: 2026-03-15
- GPU: NVIDIA GeForce RTX 3050 Ti Laptop GPU (driver 590.48.01, CUDA 13.1)
- Python: 3.12.13 (`.venv-py312`)
- Torch: 2.6.0+cu124
- Transformers: 5.3.0

## Steps executed

```bash
# Create a dedicated Python 3.12 venv (Torch does not yet ship cp313 wheels).
uv venv --python 3.12 .venv-py312
.venv-py312/bin/python -m ensurepip --upgrade

# Install Torch with CUDA 12.4 runtime (matches driver compatibility).
.venv-py312/bin/python -m pip install --upgrade --timeout 120 --retries 10 \
  --index-url https://download.pytorch.org/whl/cu124 torch==2.6.0+cu124

# Install HuggingFace stack.
.venv-py312/bin/python -m pip install "transformers>=4.30.0" "accelerate>=0.20.0" "safetensors>=0.3.0"

# Run the GPU smoke test.
.venv-py312/bin/python ForTesting/sentiment_gpu_smoke.py \
  --device cuda \
  --batch-size 8 \
  --repeats 2 \
  --model cardiffnlp/twitter-roberta-base-sentiment-latest
```

## Issues encountered and fixes

- Torch cp313 wheels are not available yet, so the default Python 3.13 environment cannot install GPU Torch.
- `.python-version` was updated to 3.12 to match the supported runtime.
- Initial Torch 2.5.1+cu121 failed to load the Cardiff NLP model because Transformers blocks `torch.load` <2.6 due to CVE-2025-32434.
- The Cardiff model does not provide safetensors weights, so upgrading to Torch 2.6+ is required for safe `.bin` loading.

## Results

- Model loaded successfully on GPU.
- Reported pipeline device: `cuda:0`.
- CUDA memory allocated: ~485 MB.
- Throughput observed: ~249 items/s (batch size 8, 2 repeats).

## Linting and type checks

- `uv run ruff check .` initially failed because `.python-version` pointed to Python 3.13 while the project now requires 3.12.
- After updating `.python-version` to 3.12, `uv run` attempted to recreate `.venv` but hit a disk error while extracting CUDA packages (no space left on device).
- Ruff and Pyrefly were run successfully using the GPU test venv after installing missing deps: `.venv-py312/bin/ruff check .` (clean) and `.venv-py312/bin/pyrefly check` (0 errors, 4 suppressed).

## Notes

- The HF Hub warned about unauthenticated requests; setting `HF_TOKEN` speeds downloads and avoids rate limits.
- For CPU fallback, run the same script with `--device cpu` or `--device auto`.
