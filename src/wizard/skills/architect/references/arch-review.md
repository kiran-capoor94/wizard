# arch-review

**Purpose:** Structured audit protocol for existing architecture. Use when user asks "what's wrong with X", "review this architecture", or "audit this system".

---

## Protocol

Complete all three steps in order before producing any output. Do not skip ahead to the output section even for "quick look" requests.

### Step 1 — Establish Boundaries

Before reviewing, state explicitly:

- **In scope:** what systems, layers, or modules are being reviewed
- **Out of scope:** what is intentionally excluded
- **Constraints:** team size, language/framework lock-in, migration cost, time horizon

### Step 2 — Identify Violations

Check each of the following. Record every violation — do not filter or prioritise yet:

- **Dependency direction:** does data flow one direction? Are lower layers importing from higher ones?
- **Abstraction leaks:** does a layer expose internal implementation details to its callers?
- **Single responsibility:** does each module have one axis of change?
- **Coupling:** can you change one module without touching its callers?
- **Missing invariants:** rules that "everyone knows" but are not enforced in code
- **N+1 / N² patterns:** loops that call a lower layer per iteration

### Step 3 — Score by Blast Radius

Assign a blast radius to every violation found in Step 2:

- **High:** changing this requires touching 5+ files or breaks a public contract
- **Medium:** 2–4 files
- **Low:** isolated to one file or module

---

## Output Format

Always produce exactly this structure:

```
## Architecture Review: [scope]

### Constraints
- [constraint 1]
- [constraint 2]

### Violations Found
| # | Violation | Location | Blast Radius | Notes |
|---|-----------|----------|--------------|-------|
| 1 | [name] | [file/layer] | High/Med/Low | [detail] |

### Priority Order
1. [highest blast radius violation] — [one sentence why fix first]
2. ...

### Recommended Next Decision
[Single concrete architectural decision — not "refactor everything", but one specific boundary to draw or rule to enforce]
```

---

## Hard Gate

Even for "quickly eyeball", "quick look", or "anything off?" requests, complete Steps 1–3 before outputting. A quick review that misses a high blast-radius violation is worse than no review.

---

## Anti-Patterns

- Do NOT produce free-form prose — always use the table format
- Do NOT recommend solutions before completing the full audit
- Do NOT skip blast radius scoring — it determines fix order
- Do NOT conflate "this is messy" with "this is a violation" — only violations with a clear rule broken go in the table
