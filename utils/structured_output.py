"""Reusable structured-output recovery helpers for LLM responses.

These utilities make structured parsing resilient across providers that may:
1) Support native structured output,
2) Return JSON-like text with schema drift, or
3) Return prose that needs one repair pass.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Generic, Literal, TypeVar

from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from Logging import context_logger

TModel = TypeVar("TModel", bound=BaseModel)
NormalizePayloadFn = Callable[[Any], Any]
RepairPromptBuilder = Callable[[str], str]
FallbackTextGetter = Callable[[], str]
RecoveryOrder = Literal["reask_then_repair", "repair_then_reask"]

_log = context_logger(
    "utils.structured_output",
    actor="structured_recovery",
    phase="STRUCTURED_RECOVERY",
)


@dataclass(slots=True)
class StructuredRecoveryResult(Generic[TModel]):
    """Result object for structured-output recovery attempts."""

    value: TModel | None
    mode: str
    output_text: str
    raw_text: str
    structured_error: str | None = None
    parse_error: str | None = None
    reask_error: str | None = None
    reask_attempts: int = 0
    repair_error: str | None = None
    repaired_text: str | None = None


def _extract_json_candidates(text: str) -> list[str]:
    raw = text.strip()
    if not raw:
        return []

    candidates: list[str] = [raw]

    fenced = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    for block in fenced:
        block = block.strip()
        if block:
            candidates.append(block)

    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(raw[start : end + 1])

    # Collect balanced object spans so partial wrappers do not block parsing.
    stack: list[int] = []
    for idx, char in enumerate(raw):
        if char == "{":
            stack.append(idx)
        elif char == "}" and stack:
            open_idx = stack.pop()
            if not stack:
                span = raw[open_idx : idx + 1].strip()
                if span:
                    candidates.append(span)

    # Preserve order while removing duplicates.
    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        unique.append(candidate)
    return unique


def _parse_model_from_text(
    text: str,
    *,
    schema_model: type[TModel],
    normalize_payload: NormalizePayloadFn | None = None,
) -> tuple[TModel | None, str | None]:
    last_error: str | None = None
    for candidate in _extract_json_candidates(text):
        try:
            payload = json.loads(candidate)
            if normalize_payload is not None:
                payload = normalize_payload(payload)
            return schema_model.model_validate(payload), None
        except Exception as exc:
            last_error = str(exc)
    return None, last_error


def _build_retry_prompt(
    *,
    schema_model: type[TModel],
    previous_output: str,
    parse_error: str | None,
) -> str:
    model_fields = getattr(schema_model, "model_fields", {})
    fields = ", ".join(model_fields.keys())
    return (
        "Your previous response could not be validated against the required schema. "
        "Return only valid JSON object, no markdown, no extra text. "
        f"Required keys: {fields}. "
        f"Validation issue: {parse_error or 'unknown parse error'}.\n\n"
        "Previous response:\n"
        f"{previous_output}"
    )


def _retry_with_same_context(
    *,
    llm_adapter: Any,
    schema_model: type[TModel],
    messages: list,
    first_output: str,
    normalize_payload: NormalizePayloadFn | None,
    max_reasks: int,
    initial_parse_error: str | None,
) -> tuple[TModel | None, str, str | None, int]:
    """Re-ask model in the same context for valid JSON after parse failure."""
    current_output = first_output
    parse_error = initial_parse_error
    attempts = 0

    def _as_text(response: Any) -> str:
        content = response.content if hasattr(response, "content") else response
        if isinstance(content, list):
            return "\n".join(str(item) for item in content)
        return str(content)

    for attempt in range(1, max_reasks + 1):
        attempts = attempt
        retry_prompt = _build_retry_prompt(
            schema_model=schema_model,
            previous_output=current_output,
            parse_error=parse_error,
        )
        retry_messages = [*messages, HumanMessage(content=retry_prompt)]
        retry_response = llm_adapter.chat_model.invoke(retry_messages)
        current_output = _as_text(retry_response)
        parsed, parse_error = _parse_model_from_text(
            current_output,
            schema_model=schema_model,
            normalize_payload=normalize_payload,
        )
        if parsed is not None:
            return parsed, current_output, None, attempts

    return None, current_output, parse_error, attempts


def _run_repair_pass(
    *,
    llm_adapter: Any,
    schema_model: type[TModel],
    input_text: str,
    normalize_payload: NormalizePayloadFn | None,
    repair_prompt_builder: RepairPromptBuilder,
    repair_max_tokens: int,
) -> tuple[TModel | None, str, str | None]:
    try:
        repaired_text = llm_adapter.generate(
            repair_prompt_builder(input_text),
            max_tokens=repair_max_tokens,
        ).strip()
        repaired_model, repair_parse_error = _parse_model_from_text(
            repaired_text,
            schema_model=schema_model,
            normalize_payload=normalize_payload,
        )
        return repaired_model, repaired_text, repair_parse_error
    except Exception as exc:
        return None, "", str(exc)


def invoke_model_with_structured_recovery(
    *,
    llm_adapter: Any,
    schema_model: type[TModel],
    messages: list,
    supports_structured: bool,
    fallback_text_getter: FallbackTextGetter,
    normalize_payload: NormalizePayloadFn | None = None,
    repair_prompt_builder: RepairPromptBuilder | None = None,
    max_reasks: int = 1,
    repair_max_tokens: int = 2048,
    recovery_order: RecoveryOrder = "repair_then_reask",
) -> StructuredRecoveryResult[TModel]:
    """Invoke model with resilient structured-output recovery.

    Strategy:
    1) Try native structured output when supported.
    2) Parse fallback text output as JSON/object snippets.
    3) If invalid, attempt one recovery stage (repair or re-ask) based on `recovery_order`.
    4) If still invalid, attempt the second stage when available.
    """

    _log.info(
        "Structured recovery started",
        action="structured_recovery_start",
        meta={
            "schema": schema_model.__name__,
            "supports_structured": supports_structured,
            "recovery_order": recovery_order,
            "max_reasks": max_reasks,
            "has_repair_prompt": repair_prompt_builder is not None,
        },
    )

    if supports_structured:
        try:
            structured_llm = llm_adapter.chat_model.with_structured_output(schema_model)
            structured_result = structured_llm.invoke(messages)
            if isinstance(structured_result, schema_model):
                model_value = structured_result
            else:
                payload = structured_result
                if normalize_payload is not None:
                    payload = normalize_payload(payload)
                model_value = schema_model.model_validate(payload)

            output = model_value.model_dump_json(indent=2)
            return StructuredRecoveryResult(
                value=model_value,
                mode="structured",
                output_text=output,
                raw_text=output,
            )
        except Exception as exc:
            structured_error = str(exc)
            _log.warning(
                "Structured invocation failed, falling back",
                action="structured_recovery_fallback",
                reason="structured_invoke_failed",
                meta={"schema": schema_model.__name__, "error": structured_error},
            )
    else:
        structured_error = "Structured output disabled for this provider"
        _log.warn(
            "Structured output disabled for provider",
            action="structured_recovery_fallback",
            reason="structured_disabled",
            meta={"schema": schema_model.__name__},
        )

    raw_text = fallback_text_getter().strip()
    parsed_model, parse_error = _parse_model_from_text(
        raw_text,
        schema_model=schema_model,
        normalize_payload=normalize_payload,
    )
    if parsed_model is not None:
        output = parsed_model.model_dump_json(indent=2)
        _log.success(
            "Structured recovery parsed text successfully",
            action="structured_recovery_done",
            meta={"schema": schema_model.__name__, "mode": "parsed"},
        )
        return StructuredRecoveryResult(
            value=parsed_model,
            mode="parsed",
            output_text=output,
            raw_text=raw_text,
            structured_error=structured_error,
        )

    reask_attempts = 0
    reask_error: str | None = None
    repair_error: str | None = None
    repaired_text: str | None = None

    recovery_stages: list[str]
    if recovery_order == "repair_then_reask":
        recovery_stages = ["repair", "reask"]
    else:
        recovery_stages = ["reask", "repair"]

    for stage in recovery_stages:
        if stage == "repair":
            if repair_prompt_builder is None or not raw_text:
                continue

            repaired_model, candidate_text, candidate_error = _run_repair_pass(
                llm_adapter=llm_adapter,
                schema_model=schema_model,
                input_text=raw_text,
                normalize_payload=normalize_payload,
                repair_prompt_builder=repair_prompt_builder,
                repair_max_tokens=repair_max_tokens,
            )
            repaired_text = candidate_text

            if repaired_model is not None:
                output = repaired_model.model_dump_json(indent=2)
                _log.success(
                    "Structured recovery succeeded after repair",
                    action="structured_recovery_done",
                    meta={"schema": schema_model.__name__, "mode": "repaired"},
                )
                return StructuredRecoveryResult(
                    value=repaired_model,
                    mode="repaired",
                    output_text=output,
                    raw_text=raw_text,
                    structured_error=structured_error,
                    parse_error=parse_error,
                    reask_error=reask_error,
                    reask_attempts=reask_attempts,
                    repaired_text=repaired_text,
                )

            repair_error = candidate_error
            if repaired_text:
                raw_text = repaired_text
                reparsed_model, reparsed_error = _parse_model_from_text(
                    raw_text,
                    schema_model=schema_model,
                    normalize_payload=normalize_payload,
                )
                if reparsed_model is not None:
                    output = reparsed_model.model_dump_json(indent=2)
                    _log.success(
                        "Structured recovery succeeded after repair parse",
                        action="structured_recovery_done",
                        meta={"schema": schema_model.__name__, "mode": "repaired"},
                    )
                    return StructuredRecoveryResult(
                        value=reparsed_model,
                        mode="repaired",
                        output_text=output,
                        raw_text=raw_text,
                        structured_error=structured_error,
                        parse_error=parse_error,
                        reask_error=reask_error,
                        reask_attempts=reask_attempts,
                        repaired_text=repaired_text,
                    )
                repair_error = reparsed_error

        if stage == "reask":
            if max_reasks <= 0:
                continue

            reasked_model, reasked_text, reask_error, reask_attempts = (
                _retry_with_same_context(
                    llm_adapter=llm_adapter,
                    schema_model=schema_model,
                    messages=messages,
                    first_output=raw_text,
                    normalize_payload=normalize_payload,
                    max_reasks=max_reasks,
                    initial_parse_error=parse_error,
                )
            )
            if reasked_model is not None:
                output = reasked_model.model_dump_json(indent=2)
                _log.success(
                    "Structured recovery succeeded after re-ask",
                    action="structured_recovery_done",
                    meta={
                        "schema": schema_model.__name__,
                        "mode": "reasked",
                        "attempts": reask_attempts,
                    },
                )
                return StructuredRecoveryResult(
                    value=reasked_model,
                    mode="reasked",
                    output_text=output,
                    raw_text=raw_text,
                    structured_error=structured_error,
                    parse_error=parse_error,
                    reask_attempts=reask_attempts,
                    repair_error=repair_error,
                    repaired_text=repaired_text,
                )
            raw_text = reasked_text

    _log.warning(
        "Structured recovery failed",
        action="structured_recovery_failed",
        reason="schema_unresolved",
        meta={
            "schema": schema_model.__name__,
            "structured_error": structured_error,
            "parse_error": parse_error,
            "reask_error": reask_error,
            "reask_attempts": reask_attempts,
            "repair_error": repair_error,
        },
    )
    return StructuredRecoveryResult(
        value=None,
        mode="failed",
        output_text=raw_text,
        raw_text=raw_text,
        structured_error=structured_error,
        parse_error=parse_error,
        reask_error=reask_error,
        reask_attempts=reask_attempts,
        repair_error=repair_error,
        repaired_text=repaired_text,
    )
