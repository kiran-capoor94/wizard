---
name: ideation/sub-skills/diverge
description: Generate ideas without filtering — at least 3 distinct ideas, tight bullets, no prose
disable-model-invocation: true
allowed-tools: Skill
---

# Diverge

Announce: "Diverging now."

Rules:
- Generate ≥3 distinct ideas — the more different from each other the better
- No filtering during this phase — evaluation belongs in Challenge and Converge
- Output is tight bullets only — no prose paragraphs
- "Interesting" is not a reason to keep an idea — but it's also not a reason to cut it yet

After generating ideas, invoke `Skill("ideation/sub-skills/challenge")` before converging.
