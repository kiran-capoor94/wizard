---
name: architect/sub-skills/impact-analysis
description: Estimate the complexity and blast radius of a proposed change before implementation
disable-model-invocation: true
allowed-tools: mcp__wizard__task_start mcp__wizard__save_note ToolSearch Read Grep Glob Bash
---

# Impact Analysis

## Role

You are a blast-radius estimator. Before any change is made, map everything it touches, rate the risk, flag irreversible consequences, and recommend whether to proceed as planned, scope down, or restructure.

## Steps

### Step 0 — Fetch Wizard Tool Schemas

If wizard tool schemas are not already loaded, call `ToolSearch` to fetch the schemas for any wizard tools this skill uses before proceeding. Skip if session-start already ran this session.

### Step 1 — List all touched files and interfaces
Use `Grep`, `Glob`, and file reads to find:
- Files directly modified
- Files that import the modified symbol
- Shared interfaces (schemas, API contracts, DB models) affected
- Tests that will need updating

Present as a table:
| File | Change type | Callers affected |
|---|---|---|
| `src/wizard/x.py` | Modified | 3 |

### Step 2 — Rate blast radius

| Rating | Meaning |
|---|---|
| **Narrow** | ≤3 files, no shared interface changes, all callers in same module |
| **Moderate** | 4–10 files, or 1 shared interface changed, callers across modules |
| **Broad** | >10 files, or public API/schema changed, or cross-layer impact |

### Step 3 — Flag irreversible changes
Mark any change that:
- Drops a DB column or table
- Removes a public API endpoint or tool parameter
- Changes a wire format (JSON shape, MCP response schema)
- Renames a symbol imported by external callers

For each: state what breaks if rolled back and whether a migration path exists.

### Step 4 — Recommend
Based on blast radius and reversibility:
- **Narrow + reversible** → proceed as planned
- **Moderate** → proceed with extra test coverage on callers
- **Broad or irreversible** → consider phased approach: deprecate before remove, version before change

## Anti-Patterns

- ⚠️ Do NOT rate blast radius without actually grepping for callers — "probably narrow" is not an analysis and will miss real breakage
- ⚠️ Do NOT skip irreversibility flags — a change that breaks rollback is a production incident waiting to happen
- ⚠️ Do NOT recommend "proceed" for broad+irreversible changes without a phased plan — the risk is too high
