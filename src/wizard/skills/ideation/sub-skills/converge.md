---
name: ideation/sub-skills/converge
description: Produce a ranked recommendation from the ideas that survived challenge
disable-model-invocation: true
allowed-tools: Skill
---

# Converge

Announce: "Converging."

Output exactly one `## Recommendation` block:

```
## Recommendation

| # | Idea | Impact | Feasibility | Notes |
|---|------|--------|-------------|-------|
| 1 | ...  | High   | Med         | ...   |
| 2 | ...  | Med    | High        | ...   |
| 3 | ...  | High   | Low         | ...   |

**Pick: Option 1** — [one sentence rationale citing constraints surfaced during elicitation]

**Why not the others:**
- Option 2: [one line]
- Option 3: [one line]

**Next step:** [single concrete action — not "think more about X" but a specific, datable thing]
```

Rules:
- The pick MUST cite at least one constraint surfaced during elicitation — not just "this feels best"
- No prose summary after this block — the table + pick + rejections + next step is the complete output
- The next step must be a specific action, not a recommendation to think
