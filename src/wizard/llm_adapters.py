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


def _coerce_note(n: dict) -> dict:
    """Coerce LLM quirks before Pydantic validation. Mutates a copy."""
    if isinstance(n.get("task_id"), list):
        # LLM returned multiple task IDs for one note — ambiguous, so drop the
        # association entirely and let the note anchor to the session instead.
        n["task_id"] = None
    return n


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
                return [SynthesisNote.model_validate(_coerce_note(n)) for n in parsed]
            except Exception as e:
                last_err = e

    logger.error("llm_adapters: failed to parse notes. Raw response: %s", raw)
    raise ValueError(f"Failed to parse LLM response: {last_err}")


def _is_local(base_url: str | None) -> bool:
    return bool(base_url and ("localhost" in base_url or "127.0.0.1" in base_url))


class OllamaAdapter:
    """Native Ollama API client using /api/chat.

    Bypasses LiteLLM to call Ollama directly, which eliminates LiteLLM's
    overhead. Uses instruction following + _parse_notes rather than
    grammar-constrained format:'json' (grammar sampling can deadlock on small
    models). Passes think:false to suppress chain-of-thought on models like
    Qwen 3.5 that enable it by default.
    """

    def __init__(self, base_url: str, model: str, options: dict):
        self._base_url = base_url.rstrip("/").removesuffix("/v1")
        # Strip the litellm provider prefix ("ollama/") — Ollama's native API
        # takes only the bare model name (e.g. "gemma4:latest-64k").
        self._model = model.removeprefix("ollama/")
        self._options = options

    def complete(self, messages: list[dict]) -> list[SynthesisNote]:
        """Call /api/chat and return validated SynthesisNotes.

        Uses instruction following and _parse_notes for robust JSON extraction.
        ValidationError for schema mismatches propagates to the caller.
        """
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            # think:false suppresses chain-of-thought on models that support it
            # (e.g. Qwen 3.5). No-op on models that don't.
            "think": False,
            # No format:"json" — grammar-constrained sampling can deadlock on small
            # models (logits for valid JSON tokens all suppressed → empty response).
            # _parse_notes handles free-form model output robustly instead.
            "options": self._options,
        }
        response = httpx.post(
            f"{self._base_url}/api/chat",
            json=payload,
            timeout=300.0,
        )
        response.raise_for_status()
        content = response.json()["message"]["content"]
        if not content or not content.strip():
            raise ValueError(
                "Ollama returned empty content — model may have failed to generate a response"
            )
        return _parse_notes(content)


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
    """Call the appropriate backend and return validated SynthesisNotes.

    Ollama backends: native /api/chat via OllamaAdapter (no LiteLLM, no grammar constraint).
    Cloud backends: LiteLLM routing by model prefix (gemini/*, openai/*, etc.).
    Local non-Ollama backends: LiteLLM with stream=False + thinking disabled.
    """
    if "ollama" in model.lower():
        options = {
            # num_ctx and num_thread deliberately omitted — both are model-loading
            # parameters. Any value that differs from the modelfile default forces
            # Ollama to destroy and reinitialise the loaded model, causing the
            # 60-120s "onboarding" delay on every synthesis call. Let Ollama pick
            # optimal values from the modelfile (num_thread via Metal on Apple Silicon).
            "num_predict": 2048,
            "temperature": 0.1,
        }
        adapter = OllamaAdapter(
            base_url or "http://localhost:11434", model, options
        )
        return adapter.complete(messages)

    kwargs: dict = {
        "model": model,
        "messages": messages,
        "timeout": 90,
        "max_tokens": 1024,
    }
    if base_url:
        kwargs["base_url"] = base_url
    if api_key:
        kwargs["api_key"] = api_key

    logger.info(
        "llm_adapters: calling %s at %s (local=%s)",
        model,
        base_url or "cloud",
        _is_local(base_url),
    )
    if _is_local(base_url):
        kwargs["stream"] = False
        kwargs["timeout"] = 300
        kwargs["extra_body"] = {"enable_thinking": False}

    response = litellm.completion(**kwargs)  # type: ignore[call-overload]
    try:
        raw = response.choices[0].message.content  # type: ignore[union-attr]
    except Exception:
        raw = getattr(response.choices[0], "text", "") or ""  # type: ignore[union-attr]

    logger.info("llm_adapters: synthesis complete (%d chars)", len(raw) if raw else 0)
    return _parse_notes(raw or "")
