#!/usr/bin/env python3
"""Whole-document-first quality judging through an existing vLLM endpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
PROMPT = (ROOT / "judge_prompt.txt").read_text(encoding="utf-8")
ENUMS = {
    "content_share": {"most", "some", "little", "uncertain"},
    "coherence": {"clear", "mixed", "broken", "uncertain"},
    "verdict": {"keep", "review", "reject"},
}
REASON_CODES = {
    "content_present",
    "boilerplate_dominant",
    "keyword_stuffing",
    "repetition_within_text",
    "incoherent_fragments",
    "deceptive_solicitation",
    "mixed_content",
    "insufficient_context",
    "unfamiliar_content",
}
MAX_QUOTE_CHARS = 400
WHITESPACE = re.compile(r"\s+")


def digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_rows(path: str | Path) -> Iterable[dict[str, str]]:
    raw = Path(path).read_text(encoding="utf-8")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = [json.loads(line) for line in raw.splitlines() if line.strip()]

    readme = value.get("_README", {}) if isinstance(value, dict) else {}
    rows = value.get("documents", [value]) if isinstance(value, dict) else value
    if not isinstance(rows, list):
        raise ValueError("Expected a JSON array, documents array, or JSONL records")
    clipping = "2500" in readme.get("text_field", "") and "truncat" in readme.get("text_field", "").lower()

    for index, row in enumerate(rows):
        text = row.get("text")
        if not isinstance(text, str):
            raise ValueError(f"Record {index} has no string text")
        coverage = row.get("coverage")
        if coverage not in {"complete", "possibly_truncated", "unknown"}:
            if row.get("is_truncated") is True:
                coverage = "possibly_truncated"
            elif row.get("is_truncated") is False:
                coverage = "complete"
            elif clipping:
                coverage = "possibly_truncated" if len(text) >= 2500 else "complete"
            else:
                coverage = "unknown"
        yield {
            "id": str(row.get("id", row.get("n", index))),
            "text": text,
            "coverage": coverage,
            "text_sha256": digest(text),
        }


def messages(text: str, coverage: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": PROMPT},
        {
            "role": "user",
            "content": json.dumps({"coverage": coverage, "text": text}, ensure_ascii=False),
        },
    ]


def strip_fence(raw: str) -> str:
    text = raw.strip()
    start = text.find("{")
    if start < 0:
        return text
    value, _ = json.JSONDecoder().raw_decode(text[start:])
    return json.dumps(value)


def normalized_whitespace(text: str) -> str:
    return WHITESPACE.sub(" ", text).strip()


def validate(answer: dict[str, Any], text: str) -> dict[str, Any]:
    optional = {"dropped_reason_codes", "dropped_evidence_count"}
    required = set(ENUMS) | {"reason_codes", "reason", "evidence"}
    if set(answer) - optional != required:
        raise ValueError("Unexpected or missing response fields")
    for field, choices in ENUMS.items():
        if answer[field] not in choices:
            raise ValueError(f"Invalid {field}")

    codes = answer["reason_codes"]
    if not isinstance(codes, list) or not codes:
        raise ValueError("Invalid reason_codes")
    dropped = [code for code in codes if code not in REASON_CODES]
    kept = [code for code in codes if code in REASON_CODES]
    if not kept:
        raise ValueError(f"Invalid reason_codes (none recognized: {codes})")
    answer["reason_codes"] = kept
    if dropped:
        answer["dropped_reason_codes"] = dropped

    reason = answer["reason"]
    if not isinstance(reason, str) or not reason.strip() or len(reason.split()) > 60:
        raise ValueError("Invalid reason")

    evidence = answer["evidence"]
    if not isinstance(evidence, list) or (text.strip() and not evidence):
        raise ValueError("Missing or invalid evidence")
    if len(evidence) > 2:
        answer["dropped_evidence_count"] = len(evidence) - 2
    flat_text = normalized_whitespace(text)
    for quote in evidence:
        if not isinstance(quote, str) or not quote.strip():
            raise ValueError("Evidence entry is empty or not a string")
        if len(quote) > MAX_QUOTE_CHARS:
            raise ValueError(f"Evidence quote too long ({len(quote)} > {MAX_QUOTE_CHARS} chars)")
        if quote not in text and normalized_whitespace(quote) not in flat_text:
            raise ValueError("Evidence is not a quote from this chunk")
    answer["evidence"] = evidence[:2]
    if answer["verdict"] == "reject" and (
        answer["content_share"] == "uncertain" or answer["coherence"] == "uncertain"
    ):
        raise ValueError("Uncertainty must go to review")
    return answer


def post(base_url: str, payload: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer EMPTY"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def is_context_error(error: urllib.error.HTTPError) -> tuple[bool, str]:
    detail = error.read().decode("utf-8", "replace")
    lowered = detail.lower()
    is_context = error.code == 400 and any(
        phrase in lowered
        for phrase in ("maximum context length", "context length", "input_tokens", "max_model_len")
    )
    return is_context, detail[:1000]


def split_near_boundary(text: str) -> int:
    midpoint = len(text) // 2
    low = max(1, len(text) // 4)
    high = min(len(text) - 1, (3 * len(text)) // 4)
    choices: list[int] = []
    for separator in ("\n", " ", "\t"):
        left = text.rfind(separator, low, midpoint + 1)
        right = text.find(separator, midpoint, high)
        if left >= low:
            choices.append(left + 1)
        if right >= 0:
            choices.append(right + 1)
        if choices:
            break
    return min(choices, key=lambda value: abs(value - midpoint)) if choices else midpoint


def request_judgment(
    text: str,
    coverage: str,
    args: argparse.Namespace,
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = {
        "model": args.model,
        "temperature": 0,
        "seed": 0,
        "max_tokens": args.max_new_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": messages(text, coverage),
    }
    started = time.monotonic()
    response = post(args.base_url, payload, args.timeout_seconds)
    choice = response["choices"][0]
    raw = choice["message"]["content"]
    usage = response.get("usage", {})
    parsed = json.loads(strip_fence(raw))
    trace = {
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "input_tokens": usage.get("prompt_tokens"),
        "generated_tokens": usage.get("completion_tokens"),
        "finish_reason": choice.get("finish_reason"),
        "raw_response": raw,
    }
    try:
        judgment = validate(parsed, text)
        trace["evidence_validation"] = "valid"
    except ValueError as error:
        if not isinstance(parsed, dict) or parsed.get("verdict") not in ENUMS["verdict"]:
            raise
        judgment = parsed
        trace["evidence_validation"] = "warning"
        trace["evidence_validation_error"] = f"{type(error).__name__}: {error}"
    return judgment, trace


def judge_piece(
    document_text: str,
    start: int,
    end: int,
    original_coverage: str,
    args: argparse.Namespace,
    depth: int,
) -> list[dict[str, Any]]:
    text = document_text[start:end]
    coverage = original_coverage if start == 0 and end == len(document_text) else "partial_chunk"
    chunk: dict[str, Any] = {"start_char": start, "end_char": end, "fallback_depth": depth}
    try:
        judgment, trace = request_judgment(text, coverage, args)
        chunk.update(trace=trace, judgment=judgment)
        return [chunk]
    except urllib.error.HTTPError as error:
        context_error, detail = is_context_error(error)
        if context_error and depth < args.max_split_depth and len(text) > 1:
            point = split_near_boundary(text)
            if 0 < point < len(text):
                return judge_piece(
                    document_text, start, start + point, original_coverage, args, depth + 1
                ) + judge_piece(
                    document_text, start + point, end, original_coverage, args, depth + 1
                )
        chunk["error"] = f"HTTPError {error.code}: {detail}"
        return [chunk]
    except (ValueError, TypeError, KeyError, OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        chunk["error"] = f"{type(error).__name__}: {error}"
        return [chunk]


def verify_coverage(text: str, chunks: list[dict[str, Any]]) -> None:
    position = 0
    for chunk in chunks:
        if chunk["start_char"] != position or chunk["end_char"] < position:
            raise ValueError("Internal chunk coverage error")
        position = chunk["end_char"]
    if position != len(text):
        raise ValueError("Internal chunk coverage does not reach document end")


def aggregate(chunks: list[dict[str, Any]], coverage: str) -> tuple[str, str]:
    if not chunks or any(chunk.get("error") for chunk in chunks):
        return "review", "inference_or_validation_error"
    verdicts = {chunk["judgment"]["verdict"] for chunk in chunks}
    if coverage != "complete":
        return "review", "incomplete_source_coverage"
    if len(verdicts) != 1 or "review" in verdicts:
        return "review", "mixed_or_uncertain_judgments"
    return next(iter(verdicts)), "consistent_chunk_judgments"


def run(args: argparse.Namespace) -> None:
    output = Path(args.output)
    if output.exists():
        raise ValueError(f"Output already exists: {output}. Choose a new path.")
    rows = list(read_rows(args.input))
    if args.limit:
        rows = rows[: args.limit]
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Input IDs must be unique")

    config = {
        "backend": "vllm_dynamic_context",
        "model": args.model,
        "base_url": args.base_url,
        "prompt_sha256": digest(PROMPT),
        "max_new_tokens": args.max_new_tokens,
        "max_split_depth": args.max_split_depth,
        "temperature": 0,
        "seed": 0,
        "enable_thinking": False,
        "strategy": "whole_document_first_then_context_error_binary_fallback",
    }
    with output.open("x", encoding="utf-8") as handle:
        for row in rows:
            chunks = judge_piece(row["text"], 0, len(row["text"]), row["coverage"], args, depth=0)
            verify_coverage(row["text"], chunks)
            decision, basis = aggregate(chunks, row["coverage"])
            result = {
                **row,
                "run": config,
                "inference_mode": (
                    "whole_document"
                    if len(chunks) == 1 and chunks[0].get("fallback_depth") == 0
                    else "fallback_chunked"
                ),
                "chunks": chunks,
                "decision": decision,
                "decision_basis": basis,
            }
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            handle.flush()
            print(row["id"], result["inference_mode"], decision, basis, flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON or JSONL document input")
    parser.add_argument("output", help="New JSONL output; must not already exist")
    parser.add_argument("--base-url", required=True, help="OpenAI-compatible base URL ending in /v1")
    parser.add_argument("--model", default="judge", help="Served model name")
    parser.add_argument("--max-new-tokens", type=int, default=768)
    parser.add_argument("--max-split-depth", type=int, default=12)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--limit", type=int, default=0, help="0 processes every document")
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be non-negative")
    if args.max_new_tokens <= 0 or args.max_split_depth < 0 or args.timeout_seconds <= 0:
        parser.error("Token, split-depth, and timeout values are invalid")
    return args


if __name__ == "__main__":
    run(parse_args())

