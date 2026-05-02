# PII scrubbing

Wizard scrubs personal data from everything it writes to its database. This happens before any write — the original values are never stored.

## What wizard scrubs automatically

Wizard detects and replaces the following:

- **NHS IDs** — formatted as `NNN NNN NNNN`
- **National Insurance numbers** — UK format (`XX999999X`)
- **Email addresses**
- **Phone numbers** — international numbers with a `+` prefix, and region-specific formats for the UK, US, Australia, Germany, and France
- **UK postcodes**
- **API keys and tokens** — Bearer tokens and strings matching the `sk-...` pattern used by OpenAI and similar services
- **Person names** — detected by context (e.g. "meeting with Sarah Jones", "assigned to Dr Smith")

Replaced values get a stub like `[EMAIL_1]`, `[SECRET_2]`, or a fake name. The counter in the stub is consistent within a session, so `[EMAIL_1]` always refers to the same original address within that session's notes.

## Consistent pseudonymisation for names

Person names are replaced with fake names, not opaque stubs. The same original name always gets the same fake replacement — across sessions, not just within one. If "Sarah Jones" becomes "Emma Clarke" in one session, she'll be "Emma Clarke" in every future session too.

This means your notes remain readable and internally consistent even after scrubbing. You can still follow a thread across sessions without the names becoming meaningless.

## How to allow a value through

If wizard is replacing something it shouldn't — your company name, a product name, a brand name — add a Python regex to the `allowlist` in `~/.wizard/config.json`:

```json
{
  "scrubbing": {
    "enabled": true,
    "allowlist": ["Acme Corp", "ProductName", "Dr\\.? Smith"]
  }
}
```

Each entry is matched as a Python regex against the original text. If a span matches any allowlist entry, it's left untouched.

A few notes on writing allowlist entries:

- Entries are full Python regex patterns, so special characters like `.` need escaping if you want them literal: `"Dr\\.? Smith"` matches both "Dr Smith" and "Dr. Smith".
- Entries are matched case-sensitively by default.
- Common tool names like Claude, Notion, Jira, GitHub, and Docker are already excluded from name detection and don't need to be added to the allowlist.

## How to disable scrubbing entirely

```json
{
  "scrubbing": {
    "enabled": false
  }
}
```

When scrubbing is disabled, content is written to the database exactly as received. This is useful in environments where you control what goes into wizard and don't want false positives at all.

## The core invariant

Original values are never stored in the database. Scrubbing happens before any write, not on read. Once a note or session summary is saved, the original PII is gone from wizard's store — there's no way to reverse it. If you need the original text, it remains in your conversation transcript.
