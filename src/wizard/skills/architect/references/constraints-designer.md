# constraints-designer

**Purpose:** Use when the user asks "what are the rules here?", "let's figure out constraints first", or when starting a new component/system design. Unnamed invariants get re-debated every session. An invariant that exists in someone's head but not in a document will be violated in code within three sprints.

---

## Protocol

Complete both steps in order. Do not proceed to schema or implementation until Step 2 output exists and the user has agreed to it.

### Step 1 — Elicit Constraints (one question at a time)

Ask exactly one question at a time in the order below. Wait for the answer before asking the next question. Do not batch questions.

**Order:**

1. **Technical constraints** — What is the DB type, transaction model, API contract, or rate limit that this module must respect?
2. **Team constraints** — What language, framework, or vendor lock-in decisions have already been made? What is the team size?
3. **Timeline constraints** — Are there hard deadlines or phased rollout requirements that constrain the design?
4. **Risk constraints** — What failure modes are unacceptable? (e.g. data loss, double-charging, PII exposure, regulatory violation)

When all four categories have been answered, declare explicitly:

> "I have enough constraints. Deriving invariants now."

Then proceed immediately to Step 2 — do not ask further clarifying questions before deriving.

### Step 2 — Derive Invariants

From the constraints collected, derive the business invariants. For each invariant:

- Give it a short, memorable **PascalCase name** (e.g. `SingleActivePlan`, `NoBackdatedCharge`)
- State the rule as: "A [entity] must always [rule]"
- State the **violation consequence** — what breaks in production if this invariant is not enforced

---

## Output Format

Always produce exactly this structure:

```
## Constraints: [scope]

### Constraints
| Type | Constraint | Source |
|------|-----------|--------|
| Technical | [constraint] | [system/vendor] |
| Team | [constraint] | [team/org decision] |
| Timeline | [constraint] | [deadline/milestone] |
| Risk | [constraint] | [failure mode] |

### Invariants
| Name | Rule | Violation consequence |
|------|------|-----------------------|
| SingleActivePlan | A subscription must always have exactly one active plan | Double-billing, incorrect feature access |

### Open Questions
[Constraints that could not be determined — name them so they are not assumed away]
```

---

## Hard Gate

Do NOT proceed to schema or implementation before producing this output and getting agreement from the user.

Time pressure is the most common reason invariants get skipped. It is also the most common reason they get violated in production. If the user says "we're in a hurry" or "let's figure it out as we go", respond:

> "Skipping this step costs more time than doing it. Unnamed invariants get violated in code within three sprints — then you debug production incidents instead of shipping features. This will take 5–10 minutes. Starting now: [first elicitation question]."

Then begin the elicitation protocol immediately.

---

## Anti-Patterns

- Do NOT mix constraints and invariants — they are different things: constraints are inputs (what you must respect), invariants are derived rules (what must always be true)
- Do NOT leave invariants unnamed — a rule without a name will not be enforced consistently across the codebase
- Do NOT skip the Open Questions section — assumed constraints are the most dangerous kind
- Do NOT jump to schema or implementation before this output is complete and agreed
- Do NOT stack multiple elicitation questions — one at a time, always
