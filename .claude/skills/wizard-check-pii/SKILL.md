---
name: wizard-check-pii
description: >
  Use when you want to check for PII leaks in the Wizard codebase. Detects raw integration data
  bypassing the Security layer and PII patterns in test fixtures. Invoke with /wizard-check-pii.
---

# PII Leak Detection

Check the Wizard codebase for PII bypass and PII in test data. Report findings in the format below.

## What To Check

### 1. Integration-to-Data Bypass

Search for import statements in files under `data/`, `services/`, `orchestrator/`, and `llm/` that import from `integrations/`.

The legal dependency flow is: `Integration → Security → Data`. Any direct import from `integrations/` into `data/`, `services/`, `orchestrator/`, or `llm/` bypasses the Security layer.

**How to check:**
- Use Grep to search for `from.*integrations/` or `require.*integrations/` in all `.ts` files under `data/`, `services/`, `orchestrator/`, and `llm/`.
- Each match is a FAIL.

### 2. PII Patterns in Test Fixtures

Search all files under `tests/` and any seed/fixture files for real-looking PII:

- **Email addresses:** Patterns like `user@example.com` are fine. Patterns like `john.smith@nhs.net`, `kiran@sisu.com`, or any email that looks like a real person are a FAIL.
- **UK phone numbers:** Patterns matching `+44`, `07\d{9}`, `01\d{9,10}`.
- **NHS numbers:** 10-digit numbers matching `\d{3}\s?\d{3}\s?\d{4}`.
- **Real names in clinical context:** Strings like "Patient John Smith" or "Dr. Jane Doe" in test data.

**How to check:**
- Use Grep with the patterns above across `tests/` and any files containing `seed`, `fixture`, or `mock` in their path.
- Real-person-looking emails and phone numbers are a FAIL. Generic placeholders (`test@test.com`, `+440000000000`) are fine.

### 3. PII Stubbing Instead of Scrubbing

Search for code that replaces PII with placeholder values (stubbing) instead of removing it entirely (scrubbing).

**How to check:**
- Use Grep for patterns like `replace.*PII`, `redact`, `mask`, `placeholder`, `[REDACTED]`, `***`, `XXX` in `security/` and `services/`.
- PII must be removed, not replaced. Any stubbing/masking logic is a FAIL.

## Output Format

Report as:

```
## PII Check

### PASS — No integration bypass detected
### FAIL — PII in test fixtures (N issues)
- tests/contracts/seed.ts:15 — real-looking email "john.smith@nhs.net"
- tests/unit/fixtures.ts:42 — NHS number pattern "123 456 7890"

### PASS — No PII stubbing detected

Result: PASS / FAIL
```

If all checks pass, report `Result: PASS`. If any check fails, report `Result: FAIL`.
