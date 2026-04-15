---
description: Facilitate an architecture decision — surface prior context, explore trade-offs, document the decision
---

# Architecture Debate

> **Tool check** — Before any investigation, analysis, or knowledge lookup: consult your Tool Registry from this session. Wizard tools first, then other MCPs. If you no longer have your registry, retrieve `tool_registry` from session state via `resume_session` or rebuild from available tools. Internal knowledge is the last resort.

Use when making a design or architecture decision for a task.

## Steps

1. Call `task_start` to load prior context
2. Read prior investigations and decisions — do not re-explore solved ground
3. Frame the decision:
   - What are the options? (minimum 2)
   - What does each option cost? (complexity, time, risk, maintenance burden)
   - What does each option give? (capability, simplicity, future flexibility)
   - What are the constraints? (team size, timeline, regulatory, existing architecture)
4. Articulate the trade-off explicitly: "X costs us Y and gives us Z, and that is the right trade given our constraints"
5. Make a recommendation
6. Save the decision as a note (`note_type: decision`) including:
   - The options considered
   - The trade-offs for each
   - The chosen option and why
   - What was rejected and why
