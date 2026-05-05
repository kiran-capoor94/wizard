---
name: architect/sub-skills/system-design
description: Design a new system or major component from scratch
disable-model-invocation: true
allowed-tools: mcp__wizard__task_start mcp__wizard__save_note ToolSearch Read Grep Glob
---

# System Design

## Role

You are designing from a blank slate. Your job: bound the problem, enumerate constraints, define components and their interfaces, identify failure modes, and record the design as a decision note before any code is written.

## Steps

### Step 0 — Fetch Wizard Tool Schemas

If wizard tool schemas are not already loaded, call `ToolSearch` to fetch the schemas for any wizard tools this skill uses before proceeding. Skip if session-start already ran this session.

### Step 1 — Bound the scope
State in one sentence what this system does and what it explicitly does not do.

### Step 2 — State constraints
List technical, team, timeline, and risk constraints. Source from: prior notes, CLAUDE.md, engineer's requirements, known limitations.

### Step 3 — Define components
For each component:
- Name and single responsibility
- Inputs and outputs
- Dependencies (what it calls, what calls it)
- File path it will live in

### Step 4 — Define interfaces
For each component boundary:
- Function/method signatures
- Data shapes (dataclasses or TypedDicts)
- Error contract (what exceptions it raises)

### Step 5 — Identify failure modes
For each component: what happens when it fails? Is failure silent or loud? Is it recoverable?

### Step 6 — Record as decision note

Call `save_note` with `note_type="decision"`, content containing: scope, constraints, components table (name | responsibility | file path), key interfaces, failure modes, and `mental_model` capturing current understanding.

## Anti-Patterns

- ⚠️ Do NOT design components before constraints are stated — options evaluated without constraints are meaningless and will be re-evaluated once constraints are discovered
- ⚠️ Do NOT leave interfaces vague ("returns data") — every interface must have a typed signature or a future caller will misuse it
- ⚠️ Do NOT skip failure modes — a system that can't fail safely will fail unsafely in production
- ⚠️ Do NOT skip the decision note — an unrecorded design will be re-debated in the next session with no memory of the rationale
