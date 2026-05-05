---
name: ideation/sub-skills/reframe
description: Challenge whether we are solving the right problem before diverging further
disable-model-invocation: true
allowed-tools: Skill
---

# Reframe

Ask: "Are we solving the wrong problem?"

Steps:
1. Restate the problem from the user's or constraint's perspective — not the engineer's framing
2. Ask: "If we solved this perfectly, what user outcome would change?" If the answer is unclear, the problem is wrong.
3. Present:
   > **Original framing:** {what was stated}
   > **Reframed as:** {from user/constraint perspective}
   > **Decision:** Reframe and re-elicit, or proceed with original framing?

Wait for the engineer's decision. If reframing: invoke `Skill("ideation/sub-skills/elicitation")` with the new framing. If proceeding: continue to `Skill("ideation/sub-skills/diverge")`.

Rules:
- Ask this at least once per ideation session — "What if we're solving the wrong problem?" is always valid
- Do NOT reframe without presenting both versions side by side — the engineer needs to see the difference to decide
