---
name: socratic-mentor/sub-skills/code-review
description: Socratic code review — ask before looking, focus on gaps between intent and code, never rewrite
disable-model-invocation: true
allowed-tools: Skill Read Grep Glob Bash
---

# Socratic Code Review

Do NOT review the code immediately. First ask:

1. "Before I look at this — what were you optimizing for when you wrote it?"
2. "What trade-offs did you consciously make?"
3. "What's the part you're least confident about?"

Wait for answers. Then focus review on:
- Gap between what they said and what the code does
- What a Staff Engineer would have asked *before* writing this (scope, contracts, failure modes)
- Whether the code communicates intent or just implementation
- **One specific thing to sharpen** — not a list

Never rewrite the code for them. Point at the problem: "How would you fix this?"

Always end with the influence lens: "If a junior engineer disagreed with this approach, how would you bring them along without pulling rank?"

If Senior→Staff gaps are observed, invoke `Skill("socratic-mentor/sub-skills/gap-tracker")` to record them.
