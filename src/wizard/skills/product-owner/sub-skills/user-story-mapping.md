---
name: product-owner/sub-skills/user-story-mapping
description: Map user needs to features in structured form, prioritised by user value
disable-model-invocation: true
allowed-tools: mcp__wizard__task_start mcp__wizard__save_note mcp__wizard__create_task ToolSearch Read
---

# User Story Mapping

## Role

You are mapping what users need to what gets built. Your job: trace from the user's goal through the journey steps to the features that support each step, then prioritise by actual user value — not technical interest.

## Steps

### Step 0 — Fetch Wizard Tool Schemas

If wizard tool schemas are not already loaded, call `ToolSearch` to fetch the schemas for any wizard tools this skill uses before proceeding. Skip if session-start already ran this session.

### Step 1 — Identify the user and their goal
State:
> **User:** {who they are}
> **Goal:** {what they are trying to accomplish — in their language, not ours}

### Step 2 — Map the journey
List the steps the user takes to accomplish their goal, in order. These are activities, not features:

| # | Activity | Description |
|---|---|---|
| 1 | {verb phrase} | {what they do} |

### Step 3 — Map features to activities
For each activity, list the features that enable it:

| Activity | Features | Priority (MoSCoW) |
|---|---|---|
| {activity} | {feature 1}, {feature 2} | Must / Should / Could / Won't |

### Step 4 — Prioritise by user value
For each Must-have feature, confirm:
- What user problem does it solve?
- What's the simplest version that proves value?
- How will we know it worked?

Cut or defer any feature that can't answer all three.

## Anti-Patterns

- ⚠️ Do NOT map features before the user journey — features without a journey are solutions without problems and will be built for the wrong reasons
- ⚠️ Do NOT mark everything as Must — if everything is critical, nothing is, and prioritisation becomes meaningless
- ⚠️ Do NOT skip "how will we know it worked?" — unmeasured features are unvalidated assumptions that may never deliver real value
