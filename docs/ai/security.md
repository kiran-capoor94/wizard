# security.md — PII scrubbing reference

Source: `src/wizard/security.py`

---

## 4-pass scrubbing pipeline

`SecurityService.scrub(content)` runs passes in this order:

| Pass | Method | Mechanism |
|------|--------|-----------|
| 1 | `_scrub_phones` | `phonenumbers.PhoneNumberMatcher(text, None)` — international numbers starting with `+` |
| 2 | `re.sub` loop over `PATTERNS` | Fixed-format regex patterns (NHS_ID, NI_NUMBER, EMAIL, POSTCODE, SECRET) |
| 3 | `_scrub_phones` | `phonenumbers.PhoneNumberMatcher` with regions `["GB", "US", "AU", "DE", "FR"]` |
| 4 | `_scrub_names` | `HeuristicNameFinder.find_spans()` + pseudonymisation via `PseudonymStore` |

**Pass 1 before Pass 2**: prevents fixed-format patterns from consuming parts of an international phone number.  
**Pass 2 before Pass 3**: protects NHS_ID format (`\d{3} \d{3} \d{4}`) from being matched as a local phone (VULN-003 fallback).

---

## `SecurityService.PATTERNS`

Five entries; all three columns are defined as `(name, regex, stub_prefix)`:

| Name | Regex | Stub prefix |
|------|-------|-------------|
| `NHS_ID` | `\b\d{3}\s\d{3}\s\d{4}\b` | `NHS_ID` |
| `NI_NUMBER` | `\b[A-Z]{2}\d{6}[A-D]\b` | `NI_NUMBER` |
| `EMAIL` | `\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z\|a-z]{2,}\b` | `EMAIL` |
| `POSTCODE` | `\b([Gg][Ii][Rr]\s?0[Aa]{2}\|[A-Za-z]{1,2}\d{1,2}[A-Za-z]?\s?\d[A-Za-z]{2})\b` | `POSTCODE` |
| `SECRET` | `(Bearer\s[A-Za-z0-9\-._~+/]+=*\|sk-[A-Za-z0-9]{20,})` | `SECRET` |

Stubs are formatted as `[{prefix}_{counter}]`, e.g. `[EMAIL_1]`, `[SECRET_2]`.

---

## `HeuristicNameFinder`

### `_HONORIFIC_RE`

```
\b(Mr|Mrs|Ms|Miss|Dr|Prof|Sir|Dame|Rev)\.?\s+(<title-word>)(?:\s+(<title-word>))?
```

Matches an honorific followed by 1–2 title-cased words. The honorific itself is captured in group 1 but excluded from the replacement span (only the name words are replaced).

### `_CONTEXT_RE`

```
(?i:meeting with|spoke with|called by|call with|speak with|assigned to|owned by|reported by|raised by|contact)\s+(<title-word>)(?:\s+(<title-word>))?
```

Matches a context trigger phrase followed by 1–2 title-cased words. Case-insensitive on the trigger phrase.

`_TITLE_WORD` pattern: `[A-Z][a-z]+'?[a-z]*|[A-Z][a-z]+`

### `_BLOCKLIST`

A `frozenset[str]` that prevents false positives. Contains:
- Month names (January–December)
- Day names (Monday–Sunday)
- Tool/brand names (Claude, Notion, Jira, Slack, GitHub, Anthropic, OpenAI, Linear, Figma, Vercel, Docker, Kubernetes, …)
- Common English words (The, This, Today, Tomorrow, Task, Note, Meeting, Session, Issue, Bug, Project, Sprint, True, False, None, …)

Any name span whose word parts appear in `_BLOCKLIST` is discarded before pseudonymisation.

### `_deduplicate`

- Sorts spans by `(start, -(end - start))` — longest span wins when two start at the same position.
- Single pass: tracks `last_end`; drops any span whose `start < last_end` (overlap).
- Returns non-overlapping spans in position order.

---

## `PseudonymStore.get_or_create`

**Key derivation**: `sha256(f"{entity_type}:{original.strip().lower()}".encode()).hexdigest()`

**Flow**:

```
1. lookup by original_hash → return fake_value if found
2. generate fake_value via generator()
3. INSERT row
   ├─ commit OK → refresh → return fake_value
   └─ IntegrityError (concurrent writer)
         → rollback
         → re-read by original_hash
         → return winner.fake_value (or fake_value if re-read misses)
4. outer except Exception → log warning → return "[PERSON_?]"
```

**Race-condition safety**: `INSERT OR IGNORE` equivalent via `IntegrityError` catch + re-read. The re-read after rollback returns the row committed by the concurrent writer; the locally-generated `fake_value` is discarded.

---

## `ScrubResult` fields

| Field | Type | Description |
|-------|------|-------------|
| `clean` | `str` | Text with all PII replaced by stubs |
| `original_to_stub` | `dict[str, str]` | Map of original PII string → replacement stub |
| `was_modified` | `bool` | `True` if `clean != content` |

---

## Two fallback paths for name pseudonymisation

| Condition | Behaviour |
|-----------|-----------|
| DB error in `PseudonymStore.get_or_create` | Returns `"[PERSON_?]"` (opaque stub; scrubbing never raises) |
| `store=None` (no `PseudonymStore` injected) | Sequential counters: `"[PERSON_1]"`, `"[PERSON_2]"`, … |

When `store=None`, `SecurityService._faker` is also `None`; the counter path in `_scrub_names` is taken.

---

## Invariant

**Scrub PII before writing to SQLite, never on read.**  
`_save_notes()` in `synthesis.py` calls `security.scrub(nd.content)` before constructing the `Note` model.
