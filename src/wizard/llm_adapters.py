"""LLM completion via litellm — synthesis backend utilities."""

from __future__ import annotations

import json
import logging
import re

import httpx
import litellm

from wizard.schemas import SynthesisNote

logger = logging.getLogger(__name__)

# Matches <think>...</think> reasoning blocks emitted by chain-of-thought models.
_THINK_RE = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)


def _strip_thinking(text: str) -> str:
    """Remove <think>…</think> chain-of-thought blocks before JSON parsing."""
    return _THINK_RE.sub("", text).strip()


def _extract_json(text: str) -> str:
    """Extract JSON from fenced code blocks or bare arrays in LLM prose output."""
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        return fenced.group(1).strip()
    bare = re.search(r"(\[[\s\S]*\])", text)
    if bare:
        return bare.group(1).strip()
    return text.strip()


def _repair_json(s: str) -> str:
    """Strip trailing commas before ] and }, wrap lone objects in an array."""
    repaired = re.sub(r",\s*\]", "]", s)
    repaired = re.sub(r",\s*\}", "}", repaired)
    if repaired.strip().startswith("{") and repaired.strip().endswith("}"):
        repaired = f"[{repaired}]"
    return repaired


def _parse_notes(raw: str) -> list[SynthesisNote]:
    """Parse LLM output into SynthesisNotes with JSON repair fallback.

    Strips thinking blocks first, then tries candidates from most-to-least
    specific (array → object → raw), applying trailing-comma repair before
    giving up.
    """
    payload = _extract_json(_strip_thinking(raw or ""))
    candidates: list[str] = []
    if "[" in payload and "]" in payload:
        start, end = payload.find("["), payload.rfind("]")
        if end > start:
            candidates.append(payload[start : end + 1])
    if "{" in payload and "}" in payload:
        start, end = payload.find("{"), payload.rfind("}")
        if end > start:
            candidates.append(payload[start : end + 1])
    candidates.append(payload)

    last_err: Exception | None = None
    for candidate in candidates:
        for attempt in (candidate, _repair_json(candidate)):
            try:
                parsed = json.loads(attempt)
                if isinstance(parsed, dict):
                    parsed = [parsed]
                return [SynthesisNote.model_validate(n) for n in parsed]
            except Exception as e:
                last_err = e
    raise ValueError(f"Failed to parse LLM response: {last_err}")


def _is_local(base_url: str | None) -> bool:
    return bool(base_url and ("localhost" in base_url or "127.0.0.1" in base_url))


def probe_backend_health(base_url: str | None) -> bool:
    """Health-check a backend.

    Only probes local servers (localhost / 127.0.0.1) — cloud APIs are
    assumed reachable and will surface errors at synthesis time if not.
    """
    if not _is_local(base_url):
        return True
    # Normalise: strip trailing /v1 so we always probe <host>/v1/models.
    probe_base = base_url.rstrip("/")  # type: ignore[union-attr]
    if probe_base.endswith("/v1"):
        probe_base = probe_base[:-3]
    try:
        r = httpx.get(probe_base + "/v1/models", timeout=2.0)
        return r.status_code in (200, 401, 403)
    except Exception:
        return False


def complete(
    model: str,
    messages: list[dict],
    base_url: str | None = None,
    api_key: str | None = None,
) -> list[SynthesisNote]:
    """Call litellm and return validated SynthesisNotes.

    litellm routes by model prefix (gemini/*, openai/*, etc.).
    For local OpenAI-compatible servers: use the openai/ prefix and include
    /v1 in base_url (e.g. http://localhost:8888/v1).

    Local servers often stream regardless of the stream param, so we force
    stream=True for localhost endpoints and collect the chunks ourselves.
    """
    kwargs: dict = {"model": model, "messages": messages}
    if base_url:
        kwargs["base_url"] = base_url
    if api_key:
        kwargs["api_key"] = api_key

    if _is_local(base_url):
        # Force streaming: local servers (Unsloth Studio) always emit SSE.
        # Disable chain-of-thought thinking to skip the reasoning preamble
        # and get the JSON response faster.
        kwargs["stream"] = True
        kwargs["extra_body"] = {"enable_thinking": False}
        response = litellm.completion(**kwargs)  # type: ignore[call-overload]
        raw = "".join(
            (chunk.choices[0].delta.content or "")  # type: ignore[union-attr]
            for chunk in response
        )
    else:
        response = litellm.completion(**kwargs)  # type: ignore[call-overload]
        try:
            raw = response.choices[0].message.content  # type: ignore[union-attr]
        except Exception:
            raw = getattr(response.choices[0], "text", "") or ""  # type: ignore[union-attr]

    return _parse_notes(raw or "")
