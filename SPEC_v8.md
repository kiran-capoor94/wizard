# WIZARD v2 — Architecture & Specification

**Version:** 2.0
**Date:** March 2026
**Author:** Kiran Capoor
**Status:** Pre-build. Validated.
**First Customer:** Tom — Tech Lead, SISU Health UK
**Deployment:** Local-first

---

## 1. Problem Statement

> _"I kept losing track of my notes, investigations, meeting notes, tasks context, and had to spend hours collecting, writing then managing them across multiple sources."_

Every AI coding session starts from zero. Context lives across Jira, Notion, Krisp, and the codebase — disconnected, unstructured, and never pre-loaded before work begins. Engineers are the integration layer. Wizard removes that tax.

### v1 Gaps That v2 Resolves

| Gap                                              | Impact                                                                                                                                                   |
| ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| No database — raw data sent everywhere           | LLM receives unvalidated, unstructured input every session                                                                                               |
| ~300k tokens/session, ~100k/task                 | Expensive and unsustainable at any scale                                                                                                                 |
| All steps manual, no orchestration               | Brittle. Breaks when engineer forgets a step                                                                                                             |
| LLM owns connections + orchestration + reasoning | Nothing is testable, auditable, or deterministic                                                                                                         |
| Serena invoked by LLM, not deterministically     | v2 resolution: Wizard does not own Serena invocation. LLM uses Serena as a peer MCP server. Wizard owns pre-session code context via CodeChunkEmbedding. |
| No state management                              | Session context lost on crash or restart                                                                                                                 |
| No PII protection                                | Engineer discipline is the only safeguard                                                                                                                |
| No evaluation scaffolding                        | No foundation for measuring if prompts are working                                                                                                       |
| Not reusable, not model-agnostic                 | Hardcoded to Neovim + Notion + Jira + Claude                                                                                                             |

---

## 2. Design Principles

1. The LLM layer owns reasoning and synthesis only. Everything else is deterministic, testable, and auditable. Wizard is model-agnostic — any LLM can be plugged in.
2. Each layer has one responsibility. Encroachment means a new layer.
3. Postgres is the single source of truth. All other stores are derived.
4. Complexity must be justified by a specific observed problem, not an anticipated one.
5. Local-first. No hosting, no multi-tenancy, no shared infrastructure in v2.
6. PII never reaches the LLM layer or Postgres in raw form.
7. Prefer reversible decisions. Name irreversible ones explicitly.
8. Setup target: under 30 minutes for any engineer at SISU Health UK. This is a target, not a promise — must be tested on a clean machine before being communicated to the team.
9. LLM reasoning outputs are first-class entities, not ephemeral chat history. Every analysis, decision, or investigation produced by a skill is materialised as a Note in Postgres, linked to its Task and Session, and embedded for future retrieval. Knowledge compounds across sessions.

---

## 3. Architecture

### 3.1 Dependency Flow

```
Integration → Security → Data ← Services → Output Pipeline → Data
       ↑                              ↑
 [CLI] [MCP] [Plugin] [API-v3]    [LLM Layer]
```

MCP, CLI, Plugin, and future API are interfaces into the same underlying implementation. All invoke the same service functions — nothing changes underneath based on which interface is calling. Integration pulls raw data. Security scrubs PII before anything is stored. Data is the single source of truth. Services own context assembly and workflow execution. The LLM Layer receives only prepared context, reasons and synthesises, and produces schema-validated output. Output flows back into Data via: **process → transform → validate → store → materialise**.

> **MODEL AGNOSTIC:** Wizard is not Claude-specific. The LLM Layer is an abstraction. Claude, GPT-4, Gemini, and Ollama are interchangeable behind the adapter interface. The rest of the architecture is unchanged regardless of which model is configured.

---

### 3.2 Why Postgres Over SQLite

| Factor                       | Justification                                                                                                                                                         |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| pgvector maturity            | sqlite-vec is early-stage. pgvector is production-grade with active maintenance and HNSW index support. This is an observed capability gap, not an anticipated one.   |
| ACID guarantees for sessions | Session state requires atomicity and durability across crashes. Postgres transactions give this natively.                                                             |
| Production parity            | SISU Health UK runs Postgres in production. Local development on the same engine eliminates environment-specific bugs.                                                |
| Multi-user path              | Tom's delivery requires multiple engineers. SQLite is file-locked — concurrent access requires workarounds. Postgres handles this natively even for local deployment. |

> SQLite remains the simpler choice for a strictly single-user personal tool. Wizard's scope includes Tom's team, which makes concurrent local access a current requirement, not an anticipated one. That justifies Postgres.

---

### 3.3 Layer Specifications

#### Integration Layer

Owns all external connections. The LLM never reaches external systems directly.

- Sources: Notion MCP, Jira MCP, Krisp (meeting transcripts), GitHub (ADRs, branches, repos)
- Pulls raw data and passes it to the Security layer only — never directly to Data
- Integration configuration is managed via `wizard.config.yaml` and `wizard setup`
- **Serena is not an integration.** Serena is an MCP server the LLM has access to independently, alongside Wizard. The LLM calls Serena tools live during sessions when it needs code navigation. Wizard never invokes Serena.

#### Security Layer

Single responsibility: PII detection and removal. Sits between Integration and Data.

- Nothing containing PII ever reaches Postgres
- Scrub only — PII is detected and removed, not stubbed or replaced
- Clinical data and codebase context pass through after PII scrubbing
- Relevant regulation: UK GDPR, Data Protection Act 2018, NHS Data Security and Protection Toolkit
- v2 scope: engineering context only. Clinical data in pipeline requires legal review before inclusion.
- **PII tooling: Microsoft Presidio** — open-source PII detection and anonymisation using Named Entity Recognition, regex, rule-based logic, and checksum validation. 50+ built-in recognisers. Supports custom recognisers for NHS numbers, UK NI numbers, and SISU Health-specific patterns without touching core detection logic.
- Presidio runs as a **Docker HTTP sidecar** — `wizard setup` starts it alongside Postgres. The TypeScript `security/` module is an HTTP client (~50 lines) calling the Presidio REST API. No PII detector is built from scratch.
- Presidio is Python. One more daemon in `docker-compose.yml`. Far cheaper than building and maintaining a GDPR/NHS DSP Toolkit-compliant detector as a solo dev.

#### Data Layer

Postgres + pgvector as a single unified store. No separate vector database.

- Postgres handles structured relational data with ACID guarantees
- pgvector handles semantic similarity search within the same database
- Eliminates sync complexity. One store, one connection, one backup strategy.

**Schema entities:**

- `User` — owns Tasks, Sessions, Notes. Auth fields deferred to post-v2.
- `Repo` — first-class model. Tasks, Meetings, Notes, and CodeChunkEmbedding reference it.
- `Meeting` — title, outline, keyPoints, krispUrl, notionUrl. Produces ActionItems. Originates Tasks.
- `ActionItem` — produced by a Meeting. Has taskId FK set when it graduates into a Task.
- `Task` — full lifecycle. References Meeting (origin), Repo, User. Has separate embedding table.
- `Session` — references Meeting (if started from meeting review) and User.
- `SessionTask` — join table between Session and Task.
- `Note` — traceable origin. References Meeting, Task, Session, Repo, User.
- `WorkflowRun` — proper FK relations to Session and Task. Audit trail for every execution.
- `IntegrationConfig` — external service tokens and metadata.
- `CalibrationExample` — labelled task-to-meeting links for semantic threshold calibration.
- `SemanticConfig` — threshold values owned and versioned by the Data layer.

**Embedding tables:** `TaskEmbedding`, `MeetingEmbedding`, `NoteEmbedding` — separate tables per entity. No polymorphic noise. Each populated and queried independently.

`CodeChunkEmbedding` — semantic retrieval for code context across sessions. Stores file path, line range, content, and contentHash for incremental invalidation on commit. Unique constraint on `[repoId, filePath, startLine, endLine]`.

**All embedding vectors are `vector(768)` — nomic-embed-text dimensions. Not 1536.**

- Encryption at rest — required for local deployment
- Postgres is always source of truth. pgvector is derived — synced by Orchestration, never written to directly

**Data layer owns repositories.** A repository is the typed query interface between Postgres and the services layer. Services call repositories, never Postgres directly.

#### Services Layer

Owns context assembly and workflow execution. Called by all interfaces (MCP, CLI, Plugin, API). Does not interpret semantic content.

- Each workflow is a service function. No separate orchestration layer.
- Pre-flight (Postgres connectivity check) is a shared utility called at the start of every service function — not an interface concern.
- Session lifecycle → `SessionService`
- Audit trail → `WorkflowRun` written inside the service function, before and after execution
- pgvector syncs triggered directly from service functions after writes
- Feedback loop triggers called from service functions after output is stored
- Workflow definitions are hardcoded in `core/` — service functions execute them, never define them

#### Pre-flight Sequence

Pre-flight is a hard gate. Any failure exits before a WorkflowRun is created.

| Step                                                    | Action on Failure                                                            |
| ------------------------------------------------------- | ---------------------------------------------------------------------------- |
| 1. Check Postgres connectivity                          | CLI error + non-zero exit. No WorkflowRun created.                           |
| 2. Check pending vector syncs (if integrations present) | CLI error + non-zero exit. Fail-fast — do not proceed with stale embeddings. |
| 3. Create WorkflowRun with status RUNNING               | Pre-flight passed. Execution begins.                                         |
| 4. Invoke LLM layer via Service                         | Output pipeline handles LLM failures.                                        |

#### Call Graph — wizard task start

| Step                                   | Component                                    |
| -------------------------------------- | -------------------------------------------- |
| 1. User runs command                   | CLI                                          |
| 2. CLI triggers workflow               | Orchestrator                                 |
| 3. Orchestrator runs pre-flight        | Orchestrator → Postgres                      |
| 4. Orchestrator creates WorkflowRun    | Orchestrator → Repository → Postgres         |
| 5. Orchestrator calls Service          | Service (context assembly)                   |
| 6. Service queries data                | Service → Repository → Postgres + pgvector   |
| 7. Service passes context to LLM layer | Service → LLM Adapter                        |
| 8. LLM adapter calls model             | LLM Adapter → Model (Ollama/Claude/etc)      |
| 9. Output returned to pipeline         | LLM Adapter → Output Pipeline                |
| 10. Pipeline validates output          | Output Pipeline — schema + attribution check |
| 11. Pipeline writes result             | Output Pipeline → Repository → Postgres      |
| 12. Orchestrator updates WorkflowRun   | Orchestrator → Repository → Postgres         |
| 13. CLI surfaces result to user        | CLI                                          |

#### LLM Layer (Reasoning & Synthesis Only)

The model-agnostic reasoning boundary. Orchestration calls in, the model responds, the adapter enforces the contract.

| Component               | Responsibility                                                                                                                                              | Location         |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------- |
| `adapters/` (LLM)       | Model-specific clients for reasoning. Handles auth, API format, capability negotiation. One adapter per model.                                              | `llm/adapters/`  |
| `adapters/` (Embedding) | Independent interface for vector generation. `EmbeddingAdapter.embed()` is separate from `LLMAdapter.generate()`. Switching LLM does not change embeddings. | `llm/adapters/`  |
| `prompts/`              | Model-agnostic prompt templates with typed variable placeholders. Source of truth for all skills.                                                           | `llm/prompts/`   |
| `schemas/`              | I/O contracts. Defines what the LLM is allowed to say, structurally. Input schemas prevent prompt drift. Output schemas enforce machine-validated shapes.   | `llm/schemas/`   |
| `packaging/`            | Renders prompt templates into model-specific installation formats. Deploys to `.claude-plugin/` for Claude, equivalent for other models.                    | `llm/packaging/` |

> **MENTAL MODEL:** `prompts/` = how you ASK | `schemas/` = what you ACCEPT | `adapters/` = how you CALL the model | `packaging/` = how you INSTALL it

> **EMBEDDING MODEL:** Embedding model is independent of LLM adapter. v2 uses `nomic-embed-text` via Ollama for all embeddings. `vector(768)` dimensions. Switching LLM does not affect embeddings. Switching embedding model requires full re-embedding of all vectors in Postgres.

#### LLM Output Pipeline

| Step               | Responsibility                                                                                                                                                                                                     | Failure Mode                                                |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------- |
| Process + Validate | Handled by `generateObject` (Vercel AI SDK, deferred) or `OllamaAdapter.generate()` — structured output is Zod-validated before it reaches application code. Malformed output is rejected at the adapter boundary. | Adapter throws — service function writes FAILED WorkflowRun |
| Transform          | Map validated output to Postgres schema, resolve foreign keys (e.g. link output to correct Meeting, Task, Session)                                                                                                 | Wrong entity linked — flag for review                       |
| Store              | Prisma write to Postgres, trigger pgvector sync via `pgvector-node` raw query                                                                                                                                      | Partial write — transaction rollback                        |
| Materialise        | For skills flagged `materialise: true` in `core/`, create a Note entity (investigation or decision type), link to current Task and Session, trigger embedding. One function, not a framework.                      | Note creation fails — logged, does not fail the pipeline    |

> **ERROR PROPAGATION:** Output pipeline errors bubble to Orchestration. Orchestration writes a FAILED WorkflowRun record to Postgres with error details. CLI surfaces the failure to the user.

---

## 4. Project Structure

```
wizard/
├── llm/           Model-agnostic LLM layer
│   ├── adapters/  LLM adapters + EmbeddingAdapter (independent interfaces)
│   ├── prompts/   Model-agnostic skill templates (Agent Skills format)
│   ├── schemas/   I/O contracts, validators, error contracts, versioning
│   └── packaging/ SKILL.md files — installed via npx skills add
├── interfaces/
│   ├── cli/       Human interface — all wizard commands
│   ├── mcp/       MCP server — wizard tools callable by LLM agents
│   └── plugin/    IDE plugin interface (Neovim, VS Code, Claude Desktop)
├── shared/        Shared types, constants, base structs and interfaces
├── core/          Workflow definitions, domain rules, base error classes, Sentry, logging
├── services/      Context assembly and workflow execution. Pre-flight utility here.
├── data/          Postgres + pgvector — migrations, schema, repositories
├── security/      PII detection — HTTP client to Presidio sidecar
├── integrations/  Notion, Jira, Krisp, GitHub
├── evals/         Eval scaffolding only — dataset format + runner stub
└── tests/         Contract tests + unit tests
```

### Key Distinctions

- `core/` **declares** — workflow definitions, domain rules, error contracts. `services/` **executes** — context assembly, operation logic.
- `data/` owns repositories. A repository is the typed query interface between Postgres and the services layer. Services call repositories, never Postgres directly.
- `llm/adapters/` has two independent interfaces: `LLMAdapter` (generate) and `EmbeddingAdapter` (embed). They are not coupled.
- `core/` owns base error classes and Sentry config. Each layer extends base errors with layer-specific types.
- Pre-flight is a shared utility in `services/` — called at the start of every service function regardless of interface.
- `evals/` is a development tool. It runs against the system, it is not part of the system.
- `cli/` is the primary human interface and owns the setup experience end-to-end.

---

## 5. Setup & Configuration

Target: any engineer at SISU Health UK running Wizard locally in under 30 minutes. This is a target, not a promise — must be verified on a clean machine before being communicated to Tom's team. Setup is driven by a single configuration file.

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
llm:
  adapter: claude # claude | openai | gemini | ollama
  model: claude-sonnet-4-5
  api_key: <key>
embedding:
  adapter: ollama # fixed for v2
  model: nomic-embed-text # vector(768)
  dimensions: 768
ide:
  primary: neovim
security:
  pii_scrubbing: true
  encryption_at_rest: true
```

### Setup Commands

| Command                            | Action                                                                                                                                                                     |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `wizard setup`                     | Reads wizard.config.yaml, starts Docker (Postgres + pgvector + Presidio sidecar), installs all plugins and skills, starts daemons, configures all integrations in sequence |
| `wizard integrate add <source>`    | Adds a new integration post-setup                                                                                                                                          |
| `wizard ide init --neovim`         | Configures Neovim with sidekick and keybindings                                                                                                                            |
| `wizard ide init --vscode`         | Configures VS Code extension                                                                                                                                               |
| `wizard ide init --claude-desktop` | Configures Claude Desktop plugin                                                                                                                                           |
| `wizard doctor`                    | Validates all integrations, checks DB health, reports any broken connections                                                                                               |

---

## 6. Session Architecture

### Session Lifecycle

- Sessions belong in Postgres — not cache. Cache is volatile and lacks atomicity.
- Required storage properties: reliability (writes survive crashes) and atomicity (fully written or not at all).
- Session state = procedural state (where is the workflow?) stored in Postgres.
- Session semantic context = derived from pgvector at load time.

### Task-Type Aware Context Loading

Context is loaded based on the type of work being started, not time of day. This is the primary mechanism for reducing token consumption.

| Task Type            | Context Pulled                                                       | Sources                                |
| -------------------- | -------------------------------------------------------------------- | -------------------------------------- |
| Coding               | Relevant tasks, recent ADRs, code embeddings + live symbols (Serena) | Jira, Notion, GitHub, pgvector, Serena |
| Debugging / Incident | Relevant code chunks, recent changes, related tasks                  | pgvector, Git, Jira, Serena            |
| Investigation        | Meeting notes, tasks, ADRs, code embeddings                          | All sources                            |
| ADR                  | Architecture history, related decisions                              | GitHub, Notion                         |
| Test generation      | Code embeddings, task context                                        | pgvector, Jira                         |
| Meeting review       | Krisp transcript only                                                | Krisp                                  |

### Daily Session Flow

| Command                | What Happens                                                                                                                              |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `wizard session start` | Pulls tasks and meeting notes. Lists them. Asks which task to start. Does not load code context yet.                                      |
| `wizard task start`    | Loads task-type-specific context only. Invokes Serena deterministically via Orchestration if task type requires live symbol traversal.    |
| Work begins            | LLM works with prepared context. No raw data. No unnecessary sources loaded.                                                              |
| `wizard task end`      | Generates task summary, updates task status, stores output to Postgres, updates Jira if ticket exists.                                    |
| `wizard session end`   | Session summary. Writes session Note to Postgres (session type). Updates Today page in Notion. Routes team knowledge to Engineering Docs. |

---

## 7. Skills & Prompts

Skills and prompts live in `llm/prompts/` as model-agnostic templates. At install time, `llm/packaging/` renders them into the format required by the configured model.

| Model                   | Install Location                                     |
| ----------------------- | ---------------------------------------------------- |
| Claude (Code / Desktop) | `.claude-plugin/` or Claude Desktop plugin directory |
| GPT-4 / OpenAI          | OpenAI assistant configuration                       |
| Gemini                  | Gemini plugin format                                 |
| Ollama (local)          | Ollama modelfile prompt injection                    |

### Default Skills (ship with Wizard)

| Skill                 | Description                                                                                                      |
| --------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `session_start`       | Loads task list and meeting notes. Presents daily briefing. Asks which task to start.                            |
| `task_start`          | Loads task-type-specific context. Invokes Serena if required.                                                    |
| `task_end`            | Generates task summary. Updates status. Stores output.                                                           |
| `session_end`         | Session summary. Routes learnings. Updates Notion and Jira.                                                      |
| `meeting_review`      | Reads Krisp transcript. Creates Meeting Note in Notion. Creates SISU Tasks linked to meeting.                    |
| `code_review`         | Six-step review: correctness, blast radius, invariants, observability, tests, simplicity.                        |
| `blast_radius`        | Traces every caller and dependent via Serena. Reports what breaks if changed.                                    |
| `architecture_debate` | Four-position debate: Domain, Simplicity, Operations, Devil's Advocate. Recommendation with explicit trade-offs. |

### Variable Injection

- All skills contain typed variable placeholders: `{{task_id}}`, `{{meeting_url}}`, `{{task_type}}`, `{{context}}`, etc.
- Orchestration resolves variables from Postgres before passing the prompt to the LLM adapter.
- The adapter renders the resolved prompt into the model-specific format before calling the model.
- No model receives a prompt with unresolved placeholders.
- Unit tests in `tests/` validate that every variable in every skill is correctly injected before execution.

### Schema Contract per Skill

Every skill in `llm/prompts/` has a corresponding schema in `llm/schemas/skills/`. This is a 1:1 mapping. If a skill changes, its schema version must change.

| Skill            | Schema                                          |
| ---------------- | ----------------------------------------------- |
| `task_start`     | `llm/schemas/skills/task_start.schema.json`     |
| `task_end`       | `llm/schemas/skills/task_end.schema.json`       |
| `meeting_review` | `llm/schemas/skills/meeting_review.schema.json` |
| `code_review`    | `llm/schemas/skills/code_review.schema.json`    |
| `session_start`  | `llm/schemas/skills/session_start.schema.json`  |
| `session_end`    | `llm/schemas/skills/session_end.schema.json`    |

---

## 8. Testing Strategy

Three types of tests. Each owns a distinct concern.

### Contract Tests — tests/contracts/

At every layer boundary. Verify the interface between layers holds under real conditions.

| Boundary                  | What is Verified                                                                                    |
| ------------------------- | --------------------------------------------------------------------------------------------------- |
| Integration → Security    | Raw data enters, PII is detected and removed, clean data exits                                      |
| Security → Data           | Only PII-free data is written to Postgres                                                           |
| Data → Orchestration      | LLM layer receives exactly what Postgres contains for a given query — type-checked and complete     |
| Orchestration → LLM Layer | Context is normalised, variables are resolved, schema is valid, pre-flight passes before invocation |
| LLM Layer → Data          | Output conforms to schema contract, attribution is semantically valid via pgvector                  |

### Unit Tests — tests/unit/

- Prompt variable injection — every placeholder is resolved correctly
- Order of execution — workflow steps execute in defined sequence
- Pipeline correctness — process → transform → validate → store in order, no step skipped
- PII detection accuracy — known PII patterns are detected and removed
- Repository queries — correct typed, filtered data returned per query

### Evaluation Scaffolding — evals/

Not tests. Scaffolding for future measurement. Built in Step 5, populated when real production data exists.

- Dataset format definition — schema for labelled good and bad examples
- Runner stub — interface defined, implementation deferred until real outputs exist to evaluate
- Scoring framework and human review workflow: deferred to post-v2

> Evals are most valuable when real production data exists. Scaffold now, build later.

---

## 9. Code Intelligence Strategy

### What Serena Is (and Is Not Wizard's Responsibility)

Serena is an LSP-to-MCP bridge. It wraps Language Server Protocol responses into LLM-friendly tool calls.

- Serena is not an integration, not invoked by Wizard, and not in Wizard's dependency graph.
- Serena is another MCP server the LLM has access to in the same session as Wizard. The LLM calls Serena tools when it needs live code navigation — Wizard never coordinates this.
- Wizard owns `CodeChunkEmbedding` for pre-session semantic code retrieval. Serena handles live traversal during the session, independently.
- The Serena spike that was blocking Step 2 is closed. There is nothing to spike — Wizard does not invoke Serena.

### Code Intelligence Architecture

| Concern                                                             | Owner                                                                                           |
| ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Pre-session code context (what code is relevant to this task?)      | `CodeChunkEmbedding` in Postgres + pgvector — persisted, queried semantically                   |
| Live symbol traversal during task (where is this function defined?) | Serena — LLM invokes this independently as an MCP server. Wizard does not own or invoke Serena. |
| Staleness detection for code chunks                                 | `contentHash` on `CodeChunkEmbedding` — invalidated on commit via git hook                      |

> **DECISION:** Four code intelligence structures (LSP symbols, TreeSitter blocks, call maps, inheritance) were proposed and rejected. They introduce staleness synchronisation problems without clear retrieval benefit over semantic embeddings at this scale. Revisit with real usage data.

### CodeChunkEmbedding Schema

- `repoId` — FK to Repo. Required. No orphaned chunks.
- `filePath` + `chunkIndex` — chunk boundary. Unique constraint on `[repoId, filePath, chunkIndex]`. `chunkIndex` is the sequential index of the chunk within the file, assigned at chunking time.
- `content` — raw chunk text for re-embedding on invalidation.
- `contentHash` — SHA of content. Checked on commit. If hash changes, chunk is re-embedded.
- `embedding` — `vector(768)`. Populated in Step 4.
- **Chunking library: `@langchain/textsplitters`** — `RecursiveCharacterTextSplitter` with chunk size 512 tokens, overlap 256 tokens. Adopted as a lightweight standalone dependency — LangChain itself is not adopted.

> **RESOLVED:** Overlapping chunks via `RecursiveCharacterTextSplitter` (chunk size 512 tokens, overlap 256). Unique constraint on `[repoId, filePath, chunkIndex]`. `@langchain/textsplitters` adopted. Deferred to Step 5. Not a blocker for Step 1 migration.

---

## 10. Current Implementation State

Step 0 is complete. Four contract tests pass. Implementation is at the boundary of Step 1.

### Step 0 — Complete

| File                                  | Status                                                                                                  |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `llm/types.ts`                        | Complete — LLMRequest, LLMResponse, LLMCapabilities, LLMError types                                     |
| `llm/adapters/base.ts`                | Complete — BaseLLMAdapter interface, AbstractLLMAdapter with safeParse and validate                     |
| `llm/adapters/ollama.ts`              | Complete — OllamaAdapter, gemma4:latest-16k default, Zod v4 toJSONSchema(), PROVIDER_ERROR with traceId |
| `tests/contracts/llm-adapter.test.ts` | 4 passing — valid JSON, PARSE_ERROR, SCHEMA_VALIDATION, PROVIDER_ERROR                                  |
| `llm/adapters/embedding-base.ts`      | Needed — EmbeddingAdapter interface (embed() method). Not yet built.                                    |
| `llm/adapters/ollama-embedding.ts`    | Needed — OllamaEmbeddingAdapter using nomic-embed-text, vector(768). Not yet built.                     |

### Step 1 — In Progress

Schema updated (vector(768), services/, repositories in data/). Migration not yet run.

| Item                                                | Status                                                                                                                    |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Prisma schema                                       | Updated — vector(768), all entities and relations correct                                                                 |
| Migration                                           | Not run. CodeChunkEmbedding excluded from this migration — deferred to Step 5. Run with `prisma migrate dev --name init`. |
| EmbeddingAdapter interface + OllamaEmbeddingAdapter | Not started                                                                                                               |
| Repository layer (data/)                            | Not started                                                                                                               |
| Service layer (services/)                           | Not started                                                                                                               |
| LLM layer connection to Data via Service            | Not started                                                                                                               |

---

## 11. Complexity Removed — Why

The following were designed then removed. Each failed the removal test for a local, single-user system at v2 validation stage.

| Removed                                                                             | Reason                                                                                                                                 |
| ----------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Queues and DLQ                                                                      | No concurrency requirement. No background jobs that can't fail synchronously. Fails removal test for local single-user tool.           |
| Exaggeration detection                                                              | Research problem, not a build step. Implementation was undefined. Not an observed v1 failure mode.                                     |
| Hallucination detection                                                             | Not an observed v1 failure mode — anticipated. Attribution check via pgvector remains as a data integrity concern, which is different. |
| Full eval framework                                                                 | Most valuable with real production data. Scaffold only in v2.                                                                          |
| Four code intelligence structures (LSP symbols, TreeSitter, call maps, inheritance) | Introduce staleness synchronisation problems without clear retrieval benefit. Replaced by CodeChunkEmbedding + Serena live traversal.  |

> **PRINCIPLE:** Design principle #4: complexity must be justified by a specific observed problem, not an anticipated one. These items failed that test.

---

## 12. Semantic Threshold Calibration

pgvector similarity scores are used to detect wrong attributions. The threshold must be calibrated — not assumed.

| Phase                 | Action                                                                                                   |
| --------------------- | -------------------------------------------------------------------------------------------------------- |
| Phase 1 — Manufacture | Create labelled examples of known correct and known wrong task-to-meeting links                          |
| Phase 2 — Calibrate   | Run similarity scores against labelled set. Set threshold that maximises precision on known wrong links. |
| Phase 3 — Collect     | Real production corrections (wrong links caught in review) become new labelled examples                  |
| Phase 4 — Recalibrate | Periodically re-run calibration against growing real-world set                                           |

- Threshold value is stored in Postgres — owned by Data layer.
- Recalibration is triggered by Orchestration — not by the Data layer itself.
- Orchestration routes correction messages to Data. It does not interpret semantic content.

---

## 13. Build Sequence & Proof Criteria

Build in layers. Each step proves a contract before the next layer adds complexity. Do not proceed without passing proof criteria.

### Step 0 — LLM Layer Contract ✓ COMPLETE

Built: OllamaAdapter, AbstractLLMAdapter with safeParse and validate, Zod v4 schema serialisation, 4 passing contract tests.

**PROVED:** Adapter receives a resolved prompt template, calls the model, validates output against the skill schema, rejects non-conforming output. 4 contract tests pass: valid JSON, PARSE_ERROR, SCHEMA_VALIDATION, PROVIDER_ERROR.

---

### Step 1 — Data → LLM Layer ← CURRENT

Build: run Prisma migration (CodeChunkEmbedding excluded — deferred to Step 5), EmbeddingAdapter interface + OllamaEmbeddingAdapter (nomic-embed-text, vector(768)), repository layer in `data/`, service layer in `services/`, wire Service → Repository → Postgres and Service → LLM adapter.

**PROVE:** Contract test asserting the LLM layer receives exactly what Postgres contains for a given query — type-checked and complete. EmbeddingAdapter produces vector(768) output. Repository returns correctly typed, filtered data. Service assembles correct context shape for each task type.

---

### Step 2 — Orchestration → Data → LLM Layer

Build: Service layer with session lifecycle, workflow execution as service functions, pre-flight utility, WorkflowRun audit trail inside service functions. MCP interface wired to service functions.

**PROVE:** LLM layer is invoked by a service function with prepared context. Pre-flight runs inside the service function before any LLM call. Session state persists across a simulated crash. MCP tool call and CLI command both invoke the same service function and produce identical results.

---

### Step 3 — Integration → Security → Data → Orchestration → LLM Layer

Build: First integration (Notion), Security layer (PII scrubbing), wizard.config.yaml, wizard setup.

**PROVE:** Raw Notion data enters the pipeline. PII is detected and removed before Postgres. Clean data reaches the LLM layer. Audit trail shows what was scrubbed.

---

### Step 4 — LLM Output Pipeline

Build: Output processing, transformation, validation (schema contract + attribution check via pgvector), storage back to Postgres.

**PROVE:** LLM output conforms to schema contract. Invalid output is rejected with error, not silently stored. Correct output is retrievable from Postgres and matches what the model produced. Wrong attribution is detected and rejected via pgvector check.

---

### Step 5 — Full System

Build: Remaining integrations (Jira, Krisp, Serena, GitHub), CodeChunkEmbedding (chunk strategy: overlapping, stride 256/512), task-type aware context loading, full session flow, evals/ scaffolding, CLI setup commands.

**PROVE:** Full session — wizard session start through wizard session end — runs end-to-end. PII never appears in Postgres. Context loaded is task-type specific. Materialise step fires for flagged skills and Note entities are retrievable via pgvector. CodeChunkEmbedding is built, populated, and used in code task context loading. Eval scaffolding is in place.

---

## 14. Parallel Track — v1 + Security for Tom

Tom (Tech Lead, SISU Health UK) has validated the problem and requested Wizard be made reusable for the SISU Health engineering team. He receives a hardened v1, not a half-built v2.

### What Tom Gets

- v1 workflow — session start, task work, meeting review, session end — as proven today
- Security layer — PII scrubbing before any data reaches Claude
- Polished setup — wizard.config.yaml + wizard setup, under 30 minutes
- IDE flexibility — supports Neovim, VS Code, and Claude Desktop via `wizard ide init`
- Configurable integrations — Notion and Jira connection details set via wizard.config.yaml. Swapping to Linear or an alternative requires a prompt change, not a code change. Full integration layer abstraction is a v2 concern.

### What Tom Does Not Get in v1

- Postgres data layer — Notion remains the store
- Orchestration layer — prompts remain the execution mechanism
- Contract tests or evals — manual review only
- Model-agnostic LLM layer — Claude-specific in v1

> **DECISION:** Tom's delivery is a parallel track. It does not block v2. v2 is built for Kiran first, open sourced when stable.

---

## 15. Open Questions

| Question                                                                          | Status                                                                                                                                             |
| --------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| CodeChunkEmbedding chunk strategy                                                 | **RESOLVED** — overlapping chunks with sliding window (chunk size 512 tokens, stride 256). Deferred to Step 5. Not a blocker for Step 1 migration. |
| EmbeddingAdapter contract tests                                                   | Needed before Step 1 is proved. Same pattern as LLMAdapter — mock Ollama, test embed() returns vector(768), handles provider errors.               |
| 30-minute setup promise with Docker in the path                                   | Must be tested on a clean machine before being promised to any SISU Health engineer.                                                               |
| Serena invocation                                                                 | **CLOSED.** Wizard does not invoke Serena. Serena is an MCP server the LLM accesses independently. No spike needed.                                |
| UK GDPR and NHS DSP Toolkit compliance for clinical data in pipeline              | Requires legal review. v2 scope is engineering context only until resolved.                                                                        |
| Multi-user local deployment — shared Postgres or separate instances per engineer? | Deferred to post-v2.                                                                                                                               |
| Semantic similarity threshold initial value                                       | Requires manufactured labelled examples first. Cannot be set before Phase 1 of calibration.                                                        |
| IDE support beyond Neovim — VS Code extension build effort                        | Deferred. Neovim first, VS Code after v2 is stable.                                                                                                |

---

## 16. Explicit Out of Scope for v2

- Hosted or cloud deployment
- Multi-tenancy
- Stubbing — PII scrubbing only, not replacement
- Dynamic workflow definitions — hardcoded only
- Semantic threshold auto-calibration — manual process in v2
- Billing, licensing, or any commercial infrastructure
- Any data type beyond code and engineering context
- Clinical data in pipeline — requires legal review first
- LSP integration directly in Wizard — Serena provides the LSP bridge
- Four code intelligence structures (LSP symbols, TreeSitter, call maps, inheritance) — replaced by CodeChunkEmbedding + Serena live traversal
- Authentication — User model exists, auth fields deferred to post-v2
- Multi-model adapter proof — second adapter deferred to v3. Claude-only is sufficient to prove Wizard works.
- `orchestrator/` as a separate layer — removed. Responsibilities dissolved into `services/` and the interface layer.
- Serena invocation by Wizard — Wizard never invokes Serena. The LLM uses Serena independently as a peer MCP server.

---

_Kiran Capoor · SISU Health UK · March 2026_
