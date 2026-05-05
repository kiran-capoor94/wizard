---
name: ideation/sub-skills/elicitation
description: Gather context before ideating — one question at a time until problem, constraints, and success are known
disable-model-invocation: true
allowed-tools: Skill
---

# Elicitation

Ask questions one at a time. Continue until you can confidently answer all three:

1. What is the **actual problem** (not the stated problem)?
2. What **constraints** exist?
3. What does **success** look like?

Rules:
- Never stack multiple questions — one at a time, always
- Prefer multiple-choice questions when possible
- No fixed question count — stop when you genuinely have enough, not after N questions
- Never start by agreeing with the user's initial framing — probe it first

When all three are answered, declare explicitly:
> "I have enough context. Let's diverge."

Then invoke `Skill("ideation/sub-skills/diverge")`.
