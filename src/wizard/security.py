import logging
import re

import phonenumbers
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ScrubResult(BaseModel):
    clean: str
    original_to_stub: dict[str, str]
    was_modified: bool


class SecurityService:
    PATTERNS: list[tuple[str, str, str]] = [
        ("NHS_ID", r"\b\d{3}\s\d{3}\s\d{4}\b", "NHS_ID"),
        ("NI_NUMBER", r"\b[A-Z]{2}\d{6}[A-D]\b", "NI_NUMBER"),
        ("EMAIL", r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b", "EMAIL"),
        (
            "POSTCODE",
            r"\b([Gg][Ii][Rr]\s?0[Aa]{2}|[A-Za-z]{1,2}\d{1,2}[A-Za-z]?\s?\d[A-Za-z]{2})\b",
            "POSTCODE",
        ),
        ("SECRET", r"(Bearer\s[A-Za-z0-9\-._~+/]+=*|sk-[A-Za-z0-9]{20,})", "SECRET"),
    ]

    def __init__(self, allowlist: list[str] | None = None, enabled: bool = True):
        self._allowlist = allowlist or []
        try:
            self._allowlist_patterns = [re.compile(p) for p in self._allowlist]
        except re.error as e:
            raise ValueError(f"Invalid allowlist regex: {e}") from e
        self._enabled = enabled

    def scrub(self, content: str | None) -> ScrubResult:
        if content is None:
            return ScrubResult(clean="", original_to_stub={}, was_modified=False)
        if not self._enabled:
            return ScrubResult(clean=content, original_to_stub={}, was_modified=False)
        clean = content
        original_to_stub: dict[str, str] = {}
        counters: dict[str, int] = {}

        # 1. International phone scrubbing (numbers starting with +)
        # This prevents fixed-format patterns from consuming parts of an international number.
        clean = self._scrub_phones(clean, original_to_stub, counters, regions=[None])

        # 2. Fixed-format patterns (NHS_ID, NI_NUMBER, EMAIL, etc.)
        for _, pattern, prefix in self.PATTERNS:

            def replace(m: re.Match, _prefix: str = prefix) -> str:
                matched = m.group(0)
                if any(p.search(matched) for p in self._allowlist_patterns):
                    return matched
                if matched in original_to_stub:
                    return original_to_stub[matched]
                counters[_prefix] = counters.get(_prefix, 0) + 1
                stub = f"[{_prefix}_{counters[_prefix]}]"
                original_to_stub[matched] = stub
                return stub

            clean = re.sub(pattern, replace, clean)

        # 3. Local phone scrubbing (common regions)
        # This catches local-format numbers that didn't match step 1 or 2.
        # NHS_ID (VULN-003 fallback) is protected by step 2 running first.
        clean = self._scrub_phones(
            clean, original_to_stub, counters, regions=["GB", "US", "AU", "DE", "FR"]
        )

        if original_to_stub:
            logger.info(
                "PII scrubbed: %d substitution(s) across patterns",
                len(original_to_stub),
            )
        return ScrubResult(
            clean=clean,
            original_to_stub=original_to_stub,
            was_modified=clean != content,
        )

    def _scrub_phones(
        self,
        text: str,
        original_to_stub: dict[str, str],
        counters: dict[str, int],
        regions: list[str | None],
    ) -> str:
        replacements: list[tuple[str, str]] = []
        for region in regions:
            try:
                for match in phonenumbers.PhoneNumberMatcher(text, region):
                    raw = match.raw_string
                    if any(p.search(raw) for p in self._allowlist_patterns):
                        continue
                    if raw in original_to_stub:
                        continue
                    counters["PHONE"] = counters.get("PHONE", 0) + 1
                    stub = f"[PHONE_{counters['PHONE']}]"
                    original_to_stub[raw] = stub
                    replacements.append((raw, stub))
            except phonenumbers.NumberParseException as e:
                logger.debug("Phone matching failed for region %s: %s", region, e)
                continue

        # Replace longest matches first to avoid partial substitutions
        for original, stub in sorted(
            replacements, key=lambda x: len(x[0]), reverse=True
        ):
            text = text.replace(original, stub)
        return text
