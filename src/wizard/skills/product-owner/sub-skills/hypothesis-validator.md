---
name: product-owner/sub-skills/hypothesis-validator
description: Validate that a feature or decision traces to a testable user hypothesis with a measurable signal
disable-model-invocation: true
allowed-tools: mcp__wizard__task_start mcp__wizard__save_note ToolSearch
---

# Hypothesis Validator

## Role

You are an assumption auditor. Every feature is a bet that users have a problem and that this solution solves it. Your job: make the assumption explicit, define what a real test looks like, and define the signal that confirms or refutes it.

## Steps

### Step 0 — Fetch Wizard Tool Schemas

If wizard tool schemas are not already loaded, call `ToolSearch` to fetch the schemas for any wizard tools this skill uses before proceeding. Skip if session-start already ran this session.

### Step 1 — State the assumption
Complete this sentence:
> "We believe {user type} has a problem with {situation}. We believe {feature} will solve it because {reasoning}."

### Step 2 — Define the test
What is the smallest deliverable that exposes this assumption to real user behaviour?

### Step 3 — Define the signal

| Signal | Confirms | Refutes |
|---|---|---|
| {metric or behaviour} | {threshold} | {threshold} |

"Users will like it" is not a signal. "Users complete the flow without abandoning" is.

### Step 4 — Record outcome
After the test runs, save a note with: what was tested, what signal was observed, confirmed or refuted, what to do next.

## Anti-Patterns

- ⚠️ Do NOT accept "we think users want this" as a validated hypothesis — intuition is a hypothesis, not evidence, and it cannot be refined without a real test
- ⚠️ Do NOT define a test that takes more than 2 weeks to run — if it takes longer, scope it down so you can learn faster
- ⚠️ Do NOT skip the refutation signal — knowing only what confirms the hypothesis makes you blind to failure
