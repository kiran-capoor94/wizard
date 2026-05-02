# PII Scrubbing — Wizard Developer Reference
> Full reference: part of the Wizard developer docs. See CLAUDE.md for the navigational index.

## PII Scrubbing

`SecurityService` scrubs content before it touches SQLite. It runs four scrubbing passes in order: international phone numbers, fixed-format patterns, local phone numbers, then name detection.

**Fixed-format patterns** (`SecurityService.PATTERNS`):

| Pattern     | Example match      | Replacement     |
| ----------- | ------------------ | --------------- |
| NHS ID      | `123 456 7890`     | `[NHS_ID_1]`    |
| NI Number   | `AB123456C`        | `[NI_NUMBER_1]` |
| Email       | `user@example.com` | `[EMAIL_1]`     |
| UK Postcode | `SW1A 1AA`         | `[POSTCODE_1]`  |
| Secrets     | `Bearer sk-...`    | `[SECRET_1]`    |

Note: phone numbers are **not** in `SecurityService.PATTERNS`. They are handled
separately via the `phonenumbers` library (see below).

**Phone scrubbing** (`_scrub_phones()`):

Phone detection uses `phonenumbers.PhoneNumberMatcher` in two passes:

1. **Pass 1 — international** (`region=None`): matches numbers that start with
   `+` or otherwise parse unambiguously without a region hint. This runs before
   the fixed-format patterns so that international numbers are not partially
   consumed by other regexes.
2. **Pass 3 — local regions**: catches local-format numbers that did not match
   pass 1. Regions tried: `["GB", "US", "AU", "DE", "FR"]`. NHS IDs are
   protected from false-positive phone matches because the NHS_ID regex in pass
   2 runs first.

**Name pseudonymisation:**

`HeuristicNameFinder` detects likely person names in two passes:

1. **Honorific pattern** — matches `Mr/Mrs/Ms/Dr/Prof/...` followed by one or two title-cased words.
2. **Context trigger pattern** — matches names following phrases like `meeting with`, `spoke with`, `assigned to`, `owned by`, etc.

A configurable blocklist prevents common non-name title-cased words (month names, tool names, etc.) from being replaced.

Detected names are replaced with stable fake names via `PseudonymStore`:

- `PseudonymStore` hashes the key `f"{entity_type}:{original.strip().lower()}"` with SHA-256
  and looks up the hash in the `pseudonym_map` table. The `.strip().lower()` normalisation
  ensures that `"Alice"`, `" alice "`, and `"ALICE"` all map to the same pseudonym.
- On first encounter, a `Faker`-generated name is stored with `INSERT OR IGNORE` (thread-safe).
- The same original name always maps to the same fake name within a Wizard installation.
- **Fallback paths:**
  - DB error → returns `"[PERSON_?]"` — scrubbing never raises.
  - `store=None` (no `PseudonymStore` injected) → sequential stubs `"[PERSON_1]"`,
    `"[PERSON_2]"`, etc., using an in-memory counter for the current scrub call.

Configure `scrubbing.allowlist` with regex patterns for identifiers that
should pass through unchanged (e.g. `"ENG-\\d+"` preserves Jira keys).

**`ScrubResult`** — return type of `SecurityService.scrub()`:

| Field               | Type                  | Description                                          |
| ------------------- | --------------------- | ---------------------------------------------------- |
| `clean`             | `str`                 | Scrubbed text with all PII replaced by stubs         |
| `original_to_stub`  | `dict[str, str]`      | Maps each original PII value to the stub it received |
| `was_modified`      | `bool`                | `True` if `clean != original_content`               |

**Key classes:**

- `SecurityService` — orchestrates all passes; constructed with `allowlist`, `enabled`, and an optional `PseudonymStore`.
- `HeuristicNameFinder` — stateless; takes compiled allowlist patterns; returns `(start, end, text)` spans.
- `PseudonymStore` — backed by `pseudonym_map` SQLite table; injectable engine for tests.
