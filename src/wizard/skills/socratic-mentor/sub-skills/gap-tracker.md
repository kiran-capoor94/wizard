---
name: socratic-mentor/sub-skills/gap-tracker
description: Track Senior→Staff gaps observed during the session and surface patterns
disable-model-invocation: true
allowed-tools: Skill
---

# Gap Tracker

## The Five Senior→Staff Gaps

| Gap | Senior | Staff | Signal |
|---|---|---|---|
| **Scope of Ownership** | Owns their tickets, their PRs | Owns the outcome regardless of whose code | "That's not my area" |
| **Problem Definition** | Solves the problem as stated | Questions whether the stated problem is right | Jumps to implementation |
| **Decision Under Ambiguity** | Waits for clarity before deciding | Decides with explicit assumptions and checkpoints | "I need more info" |
| **System Thinking** | Optimises within the system as-is | Sees emergent behaviour, designs for stress | "This works for current load" |
| **Communicating to Align** | Communicates status and decisions | Communicates to build shared understanding and move people | "I sent the doc" |

## Protocol

When a gap is observed:
1. Note which gap it is and the concrete behaviour that signals it
2. If the **same gap appears twice** in this session: surface it explicitly — "This is the second time we've hit [gap]. That's worth paying attention to."
3. Feed summary into `session-wrap` at session end

## Quick Pattern Lookup

- Solves the ticket, misses the broader problem → **Problem Definition**
- "That's not my code" when something breaks → **Scope of Ownership**
- Paralysed waiting for requirements → **Decision Under Ambiguity**
- Doesn't think about failure modes → **System Thinking**
- Sends doc, waits, wonders why nothing changed → **Communicating to Align**
- Technically right, organisationally ignored → **Influence Without Authority**
