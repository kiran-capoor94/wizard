# PII Scrubbing — Wizard Developer Reference
> Full reference: part of the Wizard developer docs. See CLAUDE.md for the navigational index.

## PII Scrubbing

`SecurityService` scrubs content before it touches SQLite. It runs four scrubbing passes in order: international phone numbers, fixed-format patterns, local phone numbers, then name detection.

**Fixed-format patterns:**

| Pattern     | Example match      | Replacement     |
| ----------- | ------------------ | --------------- |
| NHS ID      | `123 456 7890`     | `[NHS_ID_1]`    |
| NI Number   | `AB123456C`        | `[NI_NUMBER_1]` |
| Email       | `user@example.com` | `[EMAIL_1]`     |
| Phone       | `+44 7700 900000`  | `[PHONE_1]`     |
| UK Postcode | `SW1A 1AA`         | `[POSTCODE_1]`  |
| Secrets     | `Bearer sk-...`    | `[SECRET_1]`    |

Phone numbers are matched via the `phonenumbers` library for international format first, then common regions (GB, US, AU, DE, FR) for local format.

**Name pseudonymisation:**

`HeuristicNameFinder` detects likely person names in two passes:

1. **Honorific pattern** — matches `Mr/Mrs/Ms/Dr/Prof/...` followed by one or two title-cased words.
2. **Context trigger pattern** — matches names following phrases like `meeting with`, `spoke with`, `assigned to`, `owned by`, etc.

A configurable blocklist prevents common non-name title-cased words (month names, tool names, etc.) from being replaced.

Detected names are replaced with stable fake names via `PseudonymStore`:

- `PseudonymStore` hashes `entity_type:original_name` with SHA-256 and looks up the hash in the `pseudonym_map` table.
- On first encounter, a `Faker`-generated name is stored with `INSERT OR IGNORE` (thread-safe).
- The same original name always maps to the same fake name within a Wizard installation.
- On any DB error, `PseudonymStore` falls back to `[PERSON_?]` — scrubbing never raises.

Configure `scrubbing.allowlist` with regex patterns for identifiers that
should pass through unchanged (e.g. `"ENG-\\d+"` preserves Jira keys).

**Key classes:**

- `SecurityService` — orchestrates all passes; constructed with `allowlist`, `enabled`, and an optional `PseudonymStore`.
- `HeuristicNameFinder` — stateless; takes compiled allowlist patterns; returns `(start, end, text)` spans.
- `PseudonymStore` — backed by `pseudonym_map` SQLite table; injectable engine for tests.
