import re

from pydantic import BaseModel


class ScrubResult(BaseModel):
    clean: str
    stubs_applied: dict[str, str]
    was_modified: bool


class SecurityService:
    PATTERNS: list[tuple[str, str, str]] = [
        ("NHS_ID", r"\b\d{3}\s\d{3}\s\d{4}\b", "NHS_ID"),
        ("NI_NUMBER", r"\b[A-Z]{2}\d{6}[A-D]\b", "NI_NUMBER"),
        ("EMAIL", r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b", "EMAIL"),
        ("PHONE", r"\b(\+44|0)[\d\s\-]{9,13}\b", "PHONE"),
        (
            "POSTCODE",
            r"\b([Gg][Ii][Rr]\s?0[Aa]{2}|[A-Za-z]{1,2}\d{1,2}[A-Za-z]?\s?\d[A-Za-z]{2})\b",
            "POSTCODE",
        ),
        ("SECRET", r"(Bearer\s[A-Za-z0-9\-._~+/]+=*|sk-[A-Za-z0-9]{20,})", "SECRET"),
    ]

    def __init__(self, allowlist: list[str] | None = None, enabled: bool = True):
        self._allowlist = allowlist or []
        self._allowlist_patterns = [re.compile(p) for p in self._allowlist]
        self._enabled = enabled

    def scrub(self, content: str) -> ScrubResult:
        if not self._enabled:
            return ScrubResult(clean=content, stubs_applied={}, was_modified=False)
        clean = content
        stubs_applied: dict[str, str] = {}
        counters: dict[str, int] = {}

        for _name, pattern, prefix in self.PATTERNS:

            def replace(m: re.Match, _prefix: str = prefix) -> str:
                matched = m.group(0)
                if any(p.search(matched) for p in self._allowlist_patterns):
                    return matched
                if matched in stubs_applied:
                    return stubs_applied[matched]
                counters[_prefix] = counters.get(_prefix, 0) + 1
                stub = f"[{_prefix}_{counters[_prefix]}]"
                stubs_applied[matched] = stub
                return stub

            clean = re.sub(pattern, replace, clean)

        return ScrubResult(
            clean=clean,
            stubs_applied=stubs_applied,
            was_modified=clean != content,
        )
