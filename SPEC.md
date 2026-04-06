# WIZARD v2 — Architecture & Specification

**AI-Powered Engineering Workflow System**

| Field          | Value                           |
| -------------- | ------------------------------- |
| Version        | 2.0                             |
| Date           | March 2026                      |
| Author         | Kiran Capoor                    |
| Status         | Pre-build. Validated.           |
| First Customer | Tom — Tech Lead, SISU Health UK |
| Deployment     | Local-first                     |

---

## 1. Problem Statement

**PAIN**: I kept losing track of my notes, investigations, meeting notes, tasks context, and had to spend hours collecting, writing then managing them across multiple sources.

Every AI coding session starts from zero. Context lives across Jira, Notion, Krisp, and the codebase — disconnected, unstructured, and never pre-loaded before work begins. Engineers are the integration layer. Wizard removes that tax.

### v1 Gaps That v2 Resolves

| Gap                                                 | Impact                                                        |
| --------------------------------------------------- | ------------------------------------------------------------- |
| No database — raw data sent everywhere              | Claude receives unvalidated, unstructured input every session |
| ~300k tokens/session, ~100k/task                    | Expensive and unsustainable at any scale                      |
| All steps manual, no orchestration                  | Brittle. Breaks when engineer forgets a step                  |
| Claude owns connections + orchestration + reasoning | Nothing is testable, auditable, or deterministic              |
| Serena invoked by Claude, not deterministically     | Often ignored. Falls back to grep                             |
| No state management                                 | Session context lost on crash or restart                      |
| No PII protection                                   | Engineer discipline is the only safeguard                     |
| No evaluation scaffolding                           | No foundation for measuring if prompts are working            |
| Not reusable                                        | Hardcoded to Neovim + Notion + Jira                           |

---

## 2. Design Principles

1. Claude owns reasoning and synthesis only. Everything else is deterministic, testable, and auditable.
2. Each layer has one responsibility. Encroachment means a new layer.
3. Postgres is the single source of truth. All other stores are derived.
4. Complexity must be justified by a specific observed problem, not an anticipated one.
5. Local-first. No hosting, no multi-tenancy, no shared infrastructure in v2.
6. PII never reaches Claude or Postgres in raw form.
7. Prefer reversible decisions. Name irreversible ones explicitly.
8. Setup must work in under 30 minutes for any engineer at SISU Health UK.

---

## 3. Architecture

### 3.1 Dependency Flow

```
Integration → Security → Data ← Orchestration → Claude → Data
```

Integration pulls raw data. Security scrubs PII before anything is stored. Data stores clean structured data and is the single source of truth. Orchestration reads from Data, controls Claude invocation, and owns session lifecycle. Claude receives only prepared context and produces structured output. Claude's output flows back into Data via: **process → transform → validate → store**.

### 3.2 Why Postgres Over SQLite

| Factor                       | Justification                                                                                                                                                                                     |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| pgvector maturity            | sqlite-vec is early-stage. pgvector is production-grade with HNSW index support and predictable behaviour at the semantic search depth Wizard requires. Observed capability gap, not anticipated. |
| ACID guarantees for sessions | Session state requires atomicity and durability across crashes. Postgres transactions give this natively.                                                                                         |
| Production parity            | SISU Health UK runs Postgres in production. Same engine eliminates environment-specific bugs.                                                                                                     |
| Multi-user path              | Tom's delivery requires multiple engineers. SQLite is file-locked. Postgres handles concurrent local access natively.                                                                             |

> **NOTE**: SQLite remains the simpler choice for a strictly single-user personal tool. Wizard's scope includes Tom's team, which makes concurrent local access a current requirement. That justifies Postgres.

### 3.3 Layer Specifications

#### Integration Layer

- Owns all external connections. Claude never reaches external systems directly.
- Sources: Notion MCP, Jira MCP, Krisp (meeting transcripts), Serena (code intelligence), GitHub (ADRs, branches, repos)
- Serena is invoked deterministically by Orchestration — never decided by Claude at runtime
- Pulls raw data and passes it to the Security layer only — never directly to Data
- Integration configuration is managed via `wizard.config.yaml` and `wizard setup`

#### Security Layer

- Single responsibility: PII detection and removal. Sits between Integration and Data.
- Nothing containing PII ever reaches Postgres
- Scrub only — PII is detected and removed, not stubbed or replaced
- Relevant regulation: UK GDPR, Data Protection Act 2018, NHS Data Security and Protection Toolkit
- v2 scope: engineering context only. Clinical data in pipeline requires legal review before inclusion.

#### Data Layer

- Postgres + pgvector as a single unified store. No separate vector database.
- Postgres handles structured relational data with ACID guarantees
- pgvector handles semantic similarity search within the same database

**What Postgres owns:**

- Meeting notes — action items, outline, key points
- Tasks — status, due date, priority, relationships to meetings and Jira, GitHub branch/repo
- Sessions — lifecycle, context, tasks started/completed
- Authentication and tokens
- Integration configuration
- Workflow state and output
- Labelled examples for semantic threshold calibration

- Encryption at rest required for local deployment
- Postgres is always source of truth. pgvector is derived — synced by Orchestration, never written to directly.

#### Orchestration Layer

- Controls all flow. Owns runtime. Does not interpret semantic content.
- Responsibilities: DB syncs (Postgres → pgvector), pipeline execution, workflow execution, session lifecycle, audit trail, feedback loop triggers, Serena invocation

> **NOTE**: Orchestration has seven responsibilities. This is a justified exception in v2 — the responsibilities are cohesive around runtime control. Candidate for decomposition in v3 if maintenance cost justifies it.

- Workflow definitions are hardcoded in `core/` — Orchestration executes them, never defines them
- Pre-flight contract: checks Postgres consistency and triggers pending vector syncs before invoking Claude
- Claude is never invoked on stale or inconsistent data
- Serena invoked deterministically here — not by Claude

#### Claude (Reasoning & Synthesis Only)

- Receives only prepared, normalised, PII-free context from Orchestration
- Never touches raw data, external connections, or orchestration logic
- Produces structured output conforming to MCP contracts
- Interface: `plugin/` (skills and prompts with variable injection)
- Output pipeline: process → transform → validate → store
- Validation includes: schema contract check and semantic attribution check via pgvector

#### Claude Output Pipeline

| Step      | Responsibility                                            | Failure Mode                           |
| --------- | --------------------------------------------------------- | -------------------------------------- |
| Process   | Parse Claude output, extract structured fields            | Malformed output — retry or reject     |
| Transform | Map to Postgres schema, resolve foreign keys              | Wrong meeting linked — flag for review |
| Validate  | Schema contract + semantic attribution check via pgvector | Attribution failure — reject and retry |
| Store     | Write to Postgres, trigger pgvector sync                  | Partial write — transaction rollback   |

---

## 4. Project Structure

| Directory       | Responsibility                                                                                                     |
| --------------- | ------------------------------------------------------------------------------------------------------------------ |
| `plugin/`       | Claude interface — skills and prompts as templates with variable injection at execution time                       |
| `mcp/`          | MCP server — exposes Wizard capabilities to Claude Code and Claude Desktop                                         |
| `cli/`          | Human interface — `wizard init`, `wizard setup`, `wizard integrate`, `wizard ide`, `wizard session`, `wizard task` |
| `shared/`       | Shared types, hardcoded constraints, base structs and classes. Not business logic.                                 |
| `core/`         | Business and domain logic — default hardcoded workflows, prompt templates, domain rules                            |
| `orchestrator/` | Workflow execution, session lifecycle, DB sync, audit trail, feedback triggers. No queues or DLQ in v2.            |
| `data/`         | Postgres + pgvector — migrations, schema, query layer                                                              |
| `security/`     | PII detection and scrubbing                                                                                        |
| `integrations/` | Notion, Jira, Krisp, Serena, GitHub — all external connections                                                     |
| `evals/`        | Eval scaffolding only — dataset format definition and runner stub                                                  |
| `tests/`        | Contract tests at every layer boundary, unit tests for prompt injection, variable substitution, pipeline ordering  |

### Key Distinctions

- `plugin/` defines skills and prompts. Orchestration injects variables at runtime.
- `core/` defines default workflows. `orchestrator/` executes all workflows.
- `shared/` is types and constants only — not business logic.
- `evals/` is a development tool. It runs against the system, it is not part of the system.
- `cli/` is the primary human interface and owns the setup experience end-to-end.

---

## 5. Setup & Configuration

Target: any engineer at SISU Health UK running Wizard locally in under 30 minutes.

### wizard.config.yaml

```yaml
integrations:
  notion:
    token: <token>
  jira:
    token: <token>
    project: PD
  krisp:
    method: mcp
  github:
    token: <token>
ide:
  primary: neovim
security:
  pii_scrubbing: true
  encryption_at_rest: true
```

### Setup Commands

| Command                            | Action                                                                                                                            |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `wizard setup`                     | Reads wizard.config.yaml, starts Docker, installs all plugins and skills, starts daemons, configures all integrations in sequence |
| `wizard integrate add <source>`    | Adds a new integration post-setup                                                                                                 |
| `wizard ide init --neovim`         | Configures Neovim with sidekick and keybindings                                                                                   |
| `wizard ide init --vscode`         | Configures VS Code extension                                                                                                      |
| `wizard ide init --claude-desktop` | Configures Claude Desktop plugin                                                                                                  |
| `wizard doctor`                    | Validates all integrations, checks DB health, reports any broken connections                                                      |

---

## 6. Session Architecture

### Session Lifecycle

- Sessions belong in Postgres — not cache. Cache is volatile and lacks atomicity.
- Session state = procedural state (where is the workflow?) stored in Postgres.
- Session semantic context = derived from pgvector at load time.

### Task-Type Aware Context Loading

| Task Type            | Context Pulled                                 | Sources                      |
| -------------------- | ---------------------------------------------- | ---------------------------- |
| Coding               | Relevant tasks, recent ADRs, codebase (Serena) | Jira, Notion, GitHub, Serena |
| Debugging / Incident | Relevant code, recent changes, related tasks   | Serena, Git, Jira            |
| Investigation        | Meeting notes, tasks, ADRs, codebase           | All sources                  |
| ADR                  | Architecture history, related decisions        | GitHub, Notion               |
| Test generation      | Codebase, task context                         | Serena, Jira                 |
| Meeting review       | Krisp transcript only                          | Krisp                        |

### Daily Session Flow

| Command                | What Happens                                                                                                                             |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `wizard session start` | Pulls tasks and meeting notes. Lists them. Asks which task to start. Does not load code context yet.                                     |
| `wizard task start`    | Loads task-type-specific context only. Invokes Serena deterministically if task type requires it.                                        |
| Work begins            | Claude works with prepared context. No raw data. No unnecessary sources loaded.                                                          |
| `wizard task end`      | Generates task summary, updates task status, stores output to Postgres, updates Jira if ticket exists.                                   |
| `wizard session end`   | Session summary, updates Today page in Notion, routes learnings — team knowledge to Engineering Docs, personal preferences to CLAUDE.md. |

---

## 7. Skills & Prompts

Skills and prompts live in `plugin/`. They are templates — hardcoded structure with variable placeholders. Orchestration injects variables at execution time.

### Default Skills

| Skill                 | Description                                                                                                              |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `session_start`       | Loads task list and meeting notes. Presents daily briefing. Asks which task to start.                                    |
| `task_start`          | Loads task-type-specific context. Invokes Serena if required.                                                            |
| `task_end`            | Generates task summary. Updates status. Stores output.                                                                   |
| `session_end`         | Session summary. Routes learnings. Updates Notion and Jira.                                                              |
| `meeting_review`      | Reads Krisp transcript. Creates Meeting Note in Notion with Krisp URL as property. Creates SISU Tasks linked to meeting. |
| `code_review`         | Six-step review: correctness, blast radius, invariants, observability, tests, simplicity.                                |
| `blast_radius`        | Traces every caller and dependent via Serena. Reports what breaks if changed.                                            |
| `architecture_debate` | Four-position debate: Domain, Simplicity, Operations, Devil's Advocate. Recommendation with explicit trade-offs.         |

### Variable Injection

- All skills contain typed variable placeholders: `{{task_id}}`, `{{meeting_url}}`, `{{task_type}}`, `{{context}}`, etc.
- Orchestration resolves variables from Postgres before passing the prompt to Claude.
- Claude never receives a prompt with unresolved placeholders.
- Unit tests validate that every variable in every skill is correctly injected before execution.

---

## 8. Testing Strategy

### Contract Tests — `tests/contracts/`

| Boundary               | What is Verified                                                                             |
| ---------------------- | -------------------------------------------------------------------------------------------- |
| Integration → Security | Raw data enters, PII is detected and removed, clean data exits                               |
| Security → Data        | Only PII-free data is written to Postgres                                                    |
| Data → Orchestration   | Claude receives exactly what Postgres contains for a given query — type-checked and complete |
| Orchestration → Claude | Context is normalised, variables are resolved, pre-flight passes before invocation           |
| Claude → Data          | Output conforms to schema contract, attribution is semantically valid                        |

### Unit Tests — `tests/unit/`

- Prompt variable injection — every placeholder is resolved correctly
- Order of execution — workflow steps execute in defined sequence
- Pipeline correctness — process → transform → validate → store in order, no step skipped
- PII detection accuracy — known PII patterns are detected and removed

### Evaluation Scaffolding — `evals/`

- Not tests. Scaffolding for future measurement.
- Dataset format definition — schema for labelled good and bad examples
- Runner stub — interface defined, implementation deferred
- Scoring framework and human review workflow: deferred to post-v2

---

## 9. Complexity Removed — Why

| Removed                 | Reason                                                                                                                       |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Queues and DLQ          | No concurrency requirement. No background jobs that can't fail synchronously. Fails removal test for local single-user tool. |
| Exaggeration detection  | Research problem, not a build step. Not an observed v1 failure mode.                                                         |
| Hallucination detection | Not an observed v1 failure mode — anticipated. Attribution check via pgvector remains as a data integrity concern.           |
| Full eval framework     | Most valuable with real production data. Scaffold only in v2.                                                                |

> **PRINCIPLE**: Design principle #4: complexity must be justified by a specific observed problem, not an anticipated one. These four items failed that test.

---

## 10. Semantic Threshold Calibration

| Phase                 | Action                                                                                                   |
| --------------------- | -------------------------------------------------------------------------------------------------------- |
| Phase 1 — Manufacture | Create labelled examples of known correct and known wrong task-to-meeting links                          |
| Phase 2 — Calibrate   | Run similarity scores against labelled set. Set threshold that maximises precision on known wrong links. |
| Phase 3 — Collect     | Real production corrections become new labelled examples                                                 |
| Phase 4 — Recalibrate | Periodically re-run calibration against growing real-world set                                           |

- Threshold value is stored in Postgres — owned by Data layer.
- Recalibration is triggered by Orchestration — not by the Data layer itself.

---

## 11. Build Sequence & Proof Criteria

Build in layers. Each step proves a contract before the next layer adds complexity. **Do not proceed without passing proof criteria.**

### Step 1 — Data → Claude

**Build**: Postgres schema, pgvector setup, MCP interface, Claude plugin scaffold, first skill template.

**PROVE**: Contract test asserting Claude receives exactly what Postgres contains for a given query — type-checked and complete. Not just that something is returned.

### Step 2 — Orchestration → Data → Claude

**Build**: Orchestration layer, session lifecycle, basic workflow execution, pre-flight check.

**PROVE**: Claude is invoked by Orchestration with prepared context. Pre-flight check passes before invocation. Session state persists across a simulated crash.

> **OPEN QUESTION**: Serena deterministic invocation — spike needed before Step 2. Unresolved. Do not proceed to Step 2 without this.

### Step 3 — Integration → Security → Data → Orchestration → Claude

**Build**: First integration (Notion), Security layer (PII scrubbing), `wizard.config.yaml`, `wizard setup`.

**PROVE**: Raw Notion data enters the pipeline. PII is detected and removed before Postgres. Clean data reaches Claude. Audit trail shows what was scrubbed.

### Step 4 — Claude Output Pipeline

**Build**: Output processing, transformation, validation (schema contract + attribution check via pgvector), storage back to Postgres.

**PROVE**: Claude output conforms to schema contract. Invalid output is rejected with error, not silently stored. Correct output is retrievable from Postgres and matches what Claude produced. Wrong attribution is detected and rejected via pgvector check.

### Step 5 — Full System

**Build**: Remaining integrations (Jira, Krisp, Serena, GitHub), task-type aware context loading, full session flow, evals/ with first eval dataset, CLI setup commands.

**PROVE**: Full session — `wizard session start` through `wizard session end` — runs end-to-end. PII never appears in Postgres. Context loaded is task-type specific. Output is stored and traceable to its origin. Eval scaffolding is in place with dataset format defined.

---

## 12. Parallel Track — v1 + Security for Tom

Tom (Tech Lead, SISU Health UK) has validated the problem and requested Wizard be made reusable for the SISU Health engineering team. He receives a hardened v1, not a half-built v2.

### What Tom Gets

- v1 workflow — session start, task work, meeting review, session end — as proven today
- Security layer — PII scrubbing before any data reaches Claude
- Polished setup — `wizard.config.yaml` + `wizard setup`, under 30 minutes
- IDE flexibility — supports Neovim, VS Code, and Claude Desktop via `wizard ide init`
- Configurable integrations — Notion and Jira connection details set via `wizard.config.yaml`

### What Tom Does Not Get in v1

- Postgres data layer — Notion remains the store
- Orchestration layer — prompts remain the execution mechanism
- Contract tests or evals — manual review only
- Hallucination detection — engineer review

> **DECISION**: Tom's delivery is a parallel track. It does not block v2. v2 is built for Kiran first, open sourced when stable.

---

## 13. Open Questions

| Question                                                                          | Status                                                                               |
| --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| 30-minute setup promise with Docker in the path                                   | Must be tested on a clean machine before being promised to any SISU Health engineer. |
| Serena deterministic invocation                                                   | Unresolved. Do not proceed to Step 2 without this.                                   |
| UK GDPR and NHS DSP Toolkit compliance for clinical data                          | Requires legal review. v2 scope is engineering context only until resolved.          |
| Multi-user local deployment — shared Postgres or separate instances per engineer? | Deferred to post-v2.                                                                 |
| Semantic similarity threshold initial value                                       | Requires manufactured labelled examples first.                                       |
| IDE support beyond Neovim                                                         | Deferred. Neovim first, VS Code after v2 is stable.                                  |

---

## 14. Explicit Out of Scope for v2

- Hosted or cloud deployment
- Multi-tenancy
- Stubbing — PII scrubbing only, not replacement
- Dynamic workflow definitions — hardcoded only
- Semantic threshold auto-calibration — manual process in v2
- Billing, licensing, or any commercial infrastructure
- Any data type beyond code and engineering context
- Clinical data in pipeline — requires legal review first
