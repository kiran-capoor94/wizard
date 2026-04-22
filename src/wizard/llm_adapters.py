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

    logger.error("llm_adapters: failed to parse notes. Raw response: %s", raw)
    raise ValueError(f"Failed to parse LLM response: {last_err}")


def _is_local(base_url: str | None) -> bool:
    return bool(base_url and ("localhost" in base_url or "127.0.0.1" in base_url))


class OllamaAdapter:
    """Native Ollama API client using /api/chat with JSON format enforcement.

    Bypasses LiteLLM to call Ollama directly, which eliminates LiteLLM's
    overhead and allows use of Ollama's format:'json' option for reliable
    structured output.
    """

    def __init__(self, base_url: str, model: str, options: dict):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._options = options

    def complete(self, messages: list[dict]) -> list[SynthesisNote]:
        """Call /api/chat and return validated SynthesisNotes.

        format:'json' constrains Ollama to emit syntactically valid JSON.
        ValidationError for schema mismatches propagates to the caller.
        """
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": self._options,
        }
        response = httpx.post(
            f"{self._base_url}/api/chat",
            json=payload,
            timeout=300.0,
        )
        response.raise_for_status()
        content = response.json()["message"]["content"]
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            parsed = [parsed]
        return [SynthesisNote.model_validate(n) for n in parsed]


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
    kwargs: dict = {
        "model": model,
        "messages": messages,
        "timeout": 90,  # Prevent indefinite hangs (90s)
        "max_tokens": 1024,  # Synthesis should be short
    }
    if base_url:
        kwargs["base_url"] = base_url
    if api_key:
        kwargs["api_key"] = api_key

    logger.info("llm_adapters: calling %s at %s", model, base_url or "cloud")
    chunk_count = 0
    if _is_local(base_url):
        # Disable streaming for local servers to ensure the full JSON is collected.
        kwargs["stream"] = False
        kwargs["timeout"] = 300  # Allow 5 mins for local generation

        # Ollama-specific optimizations
        extra_body = {"enable_thinking": False}
        if "ollama" in model.lower():
            extra_body.update({
                "num_ctx": 16384,
                "num_predict": 512,
                "num_thread": 4,
                "flash_attention": False,
            })
        kwargs["extra_body"] = extra_body

        try:
            response = litellm.completion(**kwargs)  # type: ignore[call-overload]
            raw = response.choices[0].message.content or ""  # type: ignore[union-attr]
        except Exception as e:
            logger.error("llm_adapters: local completion failed: %s", e)
            raise
    else:
        # Cloud providers handle timeouts well.
        response = litellm.completion(**kwargs)  # type: ignore[call-overload]
        try:
            raw = response.choices[0].message.content  # type: ignore[union-attr]
        except Exception:
            raw = getattr(response.choices[0], "text", "") or ""  # type: ignore[union-attr]

    logger.info("llm_adapters: synthesis complete (%d chars, %d chunks)",
                len(raw) if raw else 0, chunk_count if _is_local(base_url) else 1)
    return _parse_notes(raw or "")
