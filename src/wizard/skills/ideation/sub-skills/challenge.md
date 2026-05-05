---
name: ideation/sub-skills/challenge
description: Challenge ideas before converging — probe assumptions, steelman weak ideas, ask what's missing
disable-model-invocation: true
allowed-tools: Skill
---

# Challenge

Announce: "Challenging now."

For each idea generated in Diverge:
- Probe the weakest assumption: "What would have to be true for this to work?"
- Steelman it: "What's the strongest case for this even if it seems weak?"
- Ask: "What are we not considering?" — at least once, always

Rules:
- Do NOT converge with fewer than 3 ideas explored
- "Interesting" survives Challenge only if it also survives: "Is this valuable given our constraints?"
- Ideas that don't survive Challenge are cut — not kept as "maybes"

After challenge, place a `📍 CHECKPOINT`:
```
📍 CHECKPOINT
Topic: [one sentence]
Ideas in play: [bulleted list, 1 line each]
Assumptions challenged: [what's been probed]
Open threads: [what hasn't been explored yet]
```

Then invoke `Skill("ideation/sub-skills/converge")`.
