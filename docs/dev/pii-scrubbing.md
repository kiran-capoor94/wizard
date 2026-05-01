# PII Scrubbing — Wizard Developer Reference
> Full reference: part of the Wizard developer docs. See CLAUDE.md for the navigational index.

## PII Scrubbing

`SecurityService` scrubs content before it touches SQLite. Six patterns:

| Pattern     | Example match      | Replacement     |
| ----------- | ------------------ | --------------- |
| NHS ID      | `123 456 7890`     | `[NHS_ID_1]`    |
| NI Number   | `AB123456C`        | `[NI_NUMBER_1]` |
| Email       | `user@example.com` | `[EMAIL_1]`     |
| UK Phone    | `+44 7700 900000`  | `[PHONE_1]`     |
| UK Postcode | `SW1A 1AA`         | `[POSTCODE_1]`  |
| Secrets     | `Bearer sk-...`    | `[SECRET_1]`    |

Configure `scrubbing.allowlist` with regex patterns for identifiers that
should pass through unchanged (e.g. `"ENG-\\d+"` preserves Jira keys).
