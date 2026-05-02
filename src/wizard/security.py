import hashlib
import logging
import re
from collections.abc import Callable

import phonenumbers
from faker import Faker
from pydantic import BaseModel
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from .database import engine as _wizard_engine
from .models import PseudonymMap

logger = logging.getLogger(__name__)


_HONORIFICS = r"(?:Mr|Mrs|Ms|Miss|Dr|Prof|Sir|Dame|Rev)\.?"

_BLOCKLIST: frozenset[str] = frozenset([
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "Claude", "Notion", "Jira", "Slack", "GitHub", "Aurora", "Postgres",
    "PostgreSQL", "Python", "Django", "FastAPI", "SQLite", "Redis", "AWS",
    "Azure", "Google", "Apple", "Microsoft", "Anthropic", "OpenAI",
    "Linear", "Confluence", "Atlassian", "Obsidian", "Krisp", "Zoom",
    "Teams", "Figma", "Vercel", "Heroku", "Docker", "Kubernetes",
    "The", "This", "That", "These", "Those", "Here", "There",
    "Today", "Tomorrow", "Yesterday", "Now", "Then",
    "Task", "Note", "Meeting", "Session", "Issue", "Bug",
    "Project", "Sprint", "Release", "Version", "Phase",
    "True", "False", "None", "Error", "Warning", "Info",
    "Wizard", "Code",
])

_TITLE_WORD = r"[A-Z][a-z]+'?[a-z]*|[A-Z][a-z]+"
_CONTEXT_TRIGGERS = (
    r"(?:meeting with|spoke with|called by|call with|speak with|"
    r"assigned to|owned by|reported by|raised by|contact)\s+"
)


class HeuristicNameFinder:
    """Detects likely person names via honorifics and context triggers.

    Returns (start, end, text) spans — non-overlapping, position order.
    """

    _HONORIFIC_RE = re.compile(
        rf"\b({_HONORIFICS})\s+({_TITLE_WORD})(?:\s+({_TITLE_WORD}))?"
    )
    _CONTEXT_RE = re.compile(
        rf"(?i:{_CONTEXT_TRIGGERS})({_TITLE_WORD})(?:\s+({_TITLE_WORD}))?"
    )

    def __init__(self, allowlist_patterns: list[re.Pattern[str]]):
        self._allowlist = allowlist_patterns

    def find_spans(self, text: str) -> list[tuple[int, int, str]]:
        raw: list[tuple[int, int, str]] = []
        raw.extend(self._honorific_spans(text))
        raw.extend(self._context_spans(text))
        return self._deduplicate(raw)

    def _honorific_spans(self, text: str) -> list[tuple[int, int, str]]:
        spans = []
        for m in self._HONORIFIC_RE.finditer(text):
            parts = [g for g in m.groups()[1:] if g]  # skip the honorific itself
            if any(p in _BLOCKLIST for p in parts):
                continue
            matched = m.group(0)
            if self._is_allowlisted(matched):
                continue
            spans.append((m.start(), m.end(), matched))
        return spans

    def _context_spans(self, text: str) -> list[tuple[int, int, str]]:
        spans = []
        for m in self._CONTEXT_RE.finditer(text):
            groups = [g for g in m.groups() if g]
            if not groups:
                continue
            if any(p in _BLOCKLIST for p in groups):
                continue
            name = " ".join(groups)
            name_start = m.start(1)
            name_end = m.end(2) if m.group(2) else m.end(1)
            if self._is_allowlisted(name):
                continue
            spans.append((name_start, name_end, name))
        return spans

    def _is_allowlisted(self, text: str) -> bool:
        return any(p.search(text) for p in self._allowlist)

    @staticmethod
    def _deduplicate(spans: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
        spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
        result: list[tuple[int, int, str]] = []
        last_end = -1
        for start, end, text in spans:
            if start >= last_end:
                result.append((start, end, text))
                last_end = end
        return result


class PseudonymStore:
    """Persistent PII-to-fake-value mapping backed by the pseudonym_map SQLite table.

    Thread-safe: INSERT OR IGNORE + re-read handles concurrent writers.
    Falls back to an opaque stub on any DB error — scrubbing never raises.
    """

    def __init__(self, engine: Engine | None = None):
        self._engine = engine if engine is not None else _wizard_engine

    def get_or_create(self, original: str, entity_type: str, generator: Callable[[], str]) -> str:
        key = f"{entity_type}:{original.strip().lower()}"
        original_hash = hashlib.sha256(key.encode()).hexdigest()
        try:
            with Session(self._engine) as session:
                existing = session.exec(
                    select(PseudonymMap).where(PseudonymMap.original_hash == original_hash)
                ).first()
                if existing:
                    return existing.fake_value
                fake_value = generator()
                row = PseudonymMap(
                    original_hash=original_hash,
                    entity_type=entity_type,
                    fake_value=fake_value,
                )
                session.add(row)
                try:
                    session.commit()
                    session.refresh(row)
                    return row.fake_value
                except IntegrityError:
                    session.rollback()
                    winner = session.exec(
                        select(PseudonymMap).where(PseudonymMap.original_hash == original_hash)
                    ).first()
                    return winner.fake_value if winner else fake_value
        except Exception as e:
            logger.warning(
                "PseudonymStore: DB error for %r, falling back to stub: %s", original, e
            )
            return "[PERSON_?]"


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

    def __init__(
        self,
        allowlist: list[str] | None = None,
        enabled: bool = True,
        store: "PseudonymStore | None" = None,
    ):
        self._allowlist = allowlist or []
        try:
            self._allowlist_patterns = [re.compile(p) for p in self._allowlist]
        except re.error as e:
            raise ValueError(f"Invalid allowlist regex: {e}") from e
        self._enabled = enabled
        self._store = store
        self._name_finder = HeuristicNameFinder(allowlist_patterns=self._allowlist_patterns)
        self._faker = Faker() if store is not None else None

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

        # 4. Name detection + pseudonymisation
        clean = self._scrub_names(clean, original_to_stub, counters)

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

    def _scrub_names(
        self,
        text: str,
        original_to_stub: dict[str, str],
        counters: dict[str, int],
    ) -> str:
        name_spans = self._name_finder.find_spans(text)
        replacements: list[tuple[str, str]] = []
        for _, _, matched in name_spans:
            if matched in original_to_stub:
                continue
            if self._store is not None and self._faker is not None:
                fake = self._store.get_or_create(matched, "PERSON", self._faker.name)
            else:
                counters["PERSON"] = counters.get("PERSON", 0) + 1
                fake = f"[PERSON_{counters['PERSON']}]"
            original_to_stub[matched] = fake
            replacements.append((matched, fake))
        for original, fake in sorted(replacements, key=lambda x: len(x[0]), reverse=True):
            text = text.replace(original, fake)
        return text

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
