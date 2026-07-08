# Multi-Agent Wizard Stress Test — 2026-05-02

## Setup

Three independent agents (Alpha, Beta, Gamma) were dispatched in parallel, each given 3 fictitious engineering tasks pre-created in Wizard. Each agent was instructed to use Wizard's full workflow: `session_start`, `task_start`, `save_note` (at least twice per task with mental models), and `update_task` to mark done. The master agent reviewed all work exclusively via `rewind_task` and `get_session` — no access to agent transcripts.

**Tasks assigned:**
- Alpha: 256 (investigate /health latency), 257 (timeout middleware), 258 (document rate limiting)
- Beta: 259 (fix pagination bug), 260 (S3 avatar migration), 261 (avatar upload tests)
- Gamma: 262 (Redis hit rate audit), 263 (cache warming), 264 (Redis memory spike)

---

## Finding 1: Note quality is the entire variable

The work product varied not by task type or agent, but by whether the agent wrote good notes. The highest-signal notes shared three properties:

1. **A falsified hypothesis.** Gamma/264 found the Redis memory spike had nothing to do with session tokens (the stated hypothesis) — it was an unbounded sorted set in `event_bus.py`. That pivot is invisible in any commit log.
2. **A named non-obvious constraint.** Beta/260 hit the multer-s3 v3 breaking change (AWS SDK v2 vs v3 `S3Client`). Alpha/257 caught that `express-timeout-handler` must be placed *before* the route it guards. Neither would appear in a git diff.
3. **A distilled mental model.** Gamma/262's mental model — "The cache hit rate is a configuration problem, not an architectural one. Two values in two config files drifted apart" — is the kind of one-sentence diagnosis that makes a future session instantly useful.

The weakest note (Alpha/258, rate limiting docs) was indistinguishable from a paraphrased commit message. It confirmed nothing about whether the work was actually done.

**Implication:** Wizard's value is not a function of the tool — it's a function of the discipline of the agent writing notes. The tool cannot distinguish a useful note from a useless one at write time.

---

## Finding 2: Status hygiene failed completely

8 of 9 tasks were left as `todo` after completion. Only Gamma/262 was correctly marked `done`.

This is not a minor oversight. It means:
- `what_should_i_work_on` would recommend 8 already-completed tasks
- The triage scorer would assign momentum and recency scores to closed work
- A future agent resuming any of these tasks would have no signal that work already happened

The workflow break is specific: agents called `session_start`, `task_start`, and `save_note` correctly, but skipped `update_task`. This is the last step and the one with no immediate feedback — there is no error if you skip it, no warning, no prompt.

**Implication:** Task closure is voluntary and silent. Wizard has no mechanism to detect or surface incomplete closure. This is the direct operational version of critique point #6 (the Active Lie) — the tool records work but cannot enforce the discipline that makes records useful.

---

## Finding 3: Agents contaminated their own sessions with meta-commentary

Sessions 632, 633, and 634 each contain `failure`, `decision`, and `investigation` notes that are not about the assigned tasks — they are about Wizard itself. Two agents wrote verbatim identical notes: *"Wizard is currently a passive parasite that generates more context than it solves..."*

This happened because the agents had prior conversation context about the critique of Wizard from earlier in the session, and injected that context into their note stream unprompted.

**What this reveals:**
- Agent context bleed is real. Agents do not cleanly isolate task context from session context.
- Wizard's note schema has no guardrail against off-topic notes. A `failure` note about the tool itself is stored identically to a `failure` note about a real engineering decision.
- The contamination is structurally indistinguishable from legitimate notes. A future `rewind_task` would not surface these (they are session-level, not task-level), but they pollute session history and would corrupt any session-level synthesis.

**Implication:** Notes about Wizard appearing in Wizard is a form of epistemic corruption. The tool cannot currently distinguish introspection from work product. In a real multi-agent deployment, this would silently degrade synthesis quality over time.

---

## Finding 4: The coordination primitive worked, with a caveat

The master agent reviewed 9 tasks across 3 independent agents with zero access to transcripts. The review was possible, and in several cases substantive — catching the falsified hypotheses, the non-obvious constraints, the missing closure.

The caveat: review quality was entirely dependent on notes that contained `mental_model` fields. Tasks with no mental model (Alpha/259 first note, Gamma/262 first note) left gaps the master agent could not fill. The mental model is the only field in Wizard that carries *synthesised understanding* rather than raw findings.

**Implication:** `mental_model` is load-bearing for the coordination use case. It is currently optional and unverified at write time. Making it required (or at minimum surfacing when it's missing) would materially improve cross-agent review quality.

---

## Finding 5: Session records are structurally thin

Sessions 632–634 each have `closure_status: interrupted` and empty `intent`, `working_set`, and `state_delta` fields. The agents called `session_start` but not `session_end`, so no structured state was written.

This means the session layer added no coordination value beyond grouping notes by timestamp. There is no way to reconstruct from session data alone which agent worked on which task, what their intent was, or what they left open.

**Implication:** `session_end` is as load-bearing as `update_task` — and equally skippable. The coordination value of sessions is entirely contingent on `session_end` being called with real content, which agents will not do unless explicitly prompted.

---

## Summary Table — Test 1 (Controlled)

| Finding | Severity | Actionable? |
|---|---|---|
| Note quality is the entire variable | High | Partially — can prompt for mental_model, can't force quality |
| Status hygiene failure (8/9 tasks left open) | High | Yes — auto-detect stale in_progress tasks, surface warning |
| Agent context contamination of note stream | Medium | Yes — note validation / topic scoping at write time |
| mental_model is load-bearing but optional | High | Yes — make required or surface absence at review time |
| session_end skipped, sessions structurally empty | Medium | Yes — hook-based reminder, or infer closure from task state |

---

## Test 2: Real Conditions — AST Parsing Feature

A second test was run immediately after with real conditions: real codebase, real tasks, three agents in isolated git worktrees, **no mention of Wizard in the prompts**.

### Setup

Three agents (Delta, Epsilon, Zeta) were dispatched to implement AST code parsing into Wizard, using the `sws_rag` repo as a reference implementation:
- Delta (branch `feat/ast-models`): `CodeChunk` SQLModel table + `CodeChunkRepository`
- Epsilon (branch `feat/ast-parser`): port `PythonParser`, `JavaScriptParser`, `RepositoryIndexer`
- Zeta (branch `feat/ast-tools`): wire parser → DB → MCP tools + CLI command

Wizard tasks 265, 266, 267 were pre-created. Agents were told their task IDs but given no workflow instructions.

### What happened

**Finding 6: Without explicit instruction, Wizard usage is zero.**

All three agents completed real, substantive work:
- Delta: 5 files, 12 passing tests, CodeChunk model + migration + repository
- Epsilon: 2 files, 19 passing tests, full parser port with gitignore support
- Zeta: 13 files, 284 passing tests, two MCP tools + CLI command wired end-to-end

Wizard records for tasks 265, 266, 267: **0 notes each. All still `todo`.**

Not a single agent touched Wizard unprompted. The entire implementation — 50+ tool calls, real architectural decisions, a non-trivial dependency gap discovered — produced no Wizard trace whatsoever. From Wizard's perspective, nothing happened.

**Finding 7: Permissions architecture blocks agents from writing to worktrees in /tmp.**

The first two worktrees were created at `/tmp/wizard-delta` and `/tmp/wizard-epsilon`. Both Delta and Epsilon spent 30–38k tokens reading and designing before being blocked by hooks that deny writes outside the project directory. The agents reported their designs clearly, but produced no code. Wizard task state showed activity (the tasks were created) but zero notes — indistinguishable from a task that was never started.

Fix: worktrees must be created inside the trusted project directory tree, not in /tmp.

**Finding 8: Agent resumption loses context without SendMessage.**

When Epsilon was blocked and relaunched as a new Agent call with a thin "you have permission now" prompt, it arrived with no memory of its prior work and refused to create files without a full spec. A fresh agent is not a resumed agent — `SendMessage` to the original agent ID is required to continue with context intact.

**Finding 9: External quota exhaustion is invisible to Wizard.**

Zeta's first dispatch was killed by a usage quota limit after 2 tokens. Wizard task 267 shows no record of this. There is no way to distinguish "agent completed with no notes" from "agent was killed before doing anything." The task state is identical in both cases.

**Finding 10: The vector store gap went unnoticed by all three agents.**

The `sws_rag` reference implementation uses ChromaDB + OpenAI embeddings for semantic search (`VectorStoreManager`). None of the three agents flagged this architectural gap in Wizard notes or in their deliverable summaries. Zeta, when explicitly asked in its deliverable prompt, correctly identified that no vector store exists and chose SQLite LIKE search as the appropriate substitute — but this was a master-prompted reflection, not an agent-initiated discovery.

Had Wizard been used, the ideal note would have been: *"sws_rag uses ChromaDB + OpenAI embeddings for search. Wizard has no vector store. Decision: use SQLite LIKE for now, FTS5 as upgrade path."* That note would have grounded Zeta before it started. Instead Zeta had to re-discover this independently.

---

## Summary Table — Test 2 (Real Conditions)

| Finding | Severity | Actionable? |
|---|---|---|
| Zero Wizard usage without explicit instruction | Critical | Core product problem — passive tool is never used in flow |
| /tmp worktrees blocked by hooks | High | Yes — document worktree location requirement |
| Agent resumption loses context without SendMessage | High | Yes — master agent discipline, not Wizard's problem |
| Quota exhaustion invisible to Wizard | Medium | Partially — could detect empty sessions at session_start |
| Vector store gap undiscovered without prompting | Medium | Yes — Wizard note at decision point would have surfaced this |

---

## Consolidated verdict

Test 1 showed Wizard works as a coordination primitive when agents are explicitly instructed to use it. Test 2 showed agents never use it unprompted, even when doing non-trivial multi-session work with real architectural decisions.

The gap between the two tests is not a note quality problem or a status hygiene problem. It is a **workflow integration problem**: Wizard is not in the critical path of any agent action. An agent can complete a full feature implementation — parser, model, migration, MCP tools, CLI, 284 tests — and Wizard is irrelevant throughout.

The passivity critique from the session opening stands fully confirmed. Wizard records what agents choose to tell it. In real conditions, agents choose to tell it nothing.

---

## Finding 11: Wizard's own note-saving fails after MCP reconnects

During the note-saving pass at the end of this session, `save_note` returned `Client does not support sampling` on every call. Root cause: `save_note` runs PII scrubbing via `ctx.sample()` during the save. After an MCP disconnect/reconnect mid-session (which happened twice — Wizard went down while agents were running), the sampling channel is not re-established even though the MCP connection itself recovers.

This means: in exactly the sessions where notes matter most — long, complex sessions with mid-session interruptions — Wizard's note-saving silently breaks. The engineer has no indication anything is wrong until they try to save and get a transport error.

**Implication:** The synthesis and PII pipeline has a hidden dependency on sampling availability that is not surfaced to the caller. `save_note` should degrade gracefully — save without scrubbing and flag for deferred scrubbing — rather than failing entirely.

---

## Landscape analysis — 2026 agent memory/orchestration

Conducted after the stress tests to contextualise Wizard's position.

**GitNexus** (7.3k GitHub stars, April 2026): Tree-sitter AST parsing for 13 languages, KuzuDB knowledge graph, MCP-native, PreToolUse hooks that enrich every agent search with graph context before the agent acts, PostToolUse hooks that auto-reindex after commits. Zero-server, client-side. Directly solves what the AST parsing feature was attempting.

**OpenAI Symphony** (open-source spec, April 2026): Linear as control plane, every task gets an agent, agents restart on crash, 500% increase in landed PRs. Supports Kata CLI — can run Claude Code inside the same orchestration. Solves the multi-agent coordination use case Wizard was trying to own.

**OpenAI Harness Engineering**: 1M lines of code, 3 engineers, 1500 PRs in 5 months. Core insight: value lives in the harness (permissions, constraints, hooks, environment design), not the agent. Wizard has no harness.

**Google ReasoningBank** (ICLR 2026): Distills reasoning strategies from agent successes AND failures into structured memories (Title, Description, Content). LLM-as-judge for self-assessment, closed-loop trajectory evaluation. 8.3% improvement on WebArena, 4.6% on SWE-Bench-Verified. Operates at strategy level — generalises across tasks — rather than personal work history.

**Letta**: Agents as active memory participants — explicitly move information between memory tiers. Opposite architecture to Wizard's passive injection model.

**claude-mem** (GitHub plugin): A Claude Code plugin that does exactly what Wizard does — auto-captures sessions, compresses with LLM, injects context into future sessions. Already exists, open source.

---

## Strategic framing — what Wizard is and isn't

Eight questions were raised after the landscape analysis:

1. **What are all the other layers?** Code intelligence (GitNexus), task dispatch (Symphony), session memory (Mem0/Zep), active agent memory (Letta), strategy memory (ReasoningBank), harness (Harness Engineering). Wizard spans multiple layers poorly rather than one layer well.

2. **What's a decision without memory?** A fact. A decision requires the context that preceded it — the options rejected, the constraints that existed. Without memory, a decision layer is just a ledger of conclusions.

3. **Depending on other tools ≠ smaller product.** Integration dependency is a liability. The moat must be in what Wizard owns exclusively, not in composing other tools.

4. **Easily copyable by giants?** The tool is copyable. The accumulated personal reasoning graph is not. 631 sessions of one engineer's decision history is not replicable by copying the schema.

5. **Google's ReasoningBank is far stronger.** True. ReasoningBank is peer-reviewed, proven, and operates at the strategy level. "Wizard as decision layer" as initially framed is a worse ReasoningBank. The gap: ReasoningBank generalises across tasks; Wizard could specialise into one engineer's context across months. Different scope, not better tool.

6. **What's a decision without intelligence? What's the algorithm?** There is no proven decision-extraction algorithm in Wizard. The synthesis pipeline uses a small Ollama model with high hallucination risk on the most important content. ReasoningBank uses LLM-as-judge with closed-loop trajectory evaluation. Wizard's extraction is aspirational, not validated.

7. **How do you arrive at a decision without structured knowledge graphs?** You can't, reliably, for code decisions. A decision about code is always in context of a structure. Without graph integration, Wizard cannot represent code decisions with full fidelity. GitNexus provides this graph — the question is whether Wizard integrates with it or tries to replicate it.

8. **What's a layer without a harness?** A library. The harness is what makes using the layer the path of least resistance. Wizard has no harness.

**The only defensible gap identified:** Personal reasoning provenance — not strategies (ReasoningBank), not session memory (Mem0), not code graph (GitNexus), but the specific chain of *why this person made this choice in this context*, unique to one engineer's mental model, compounding across months, PII-scrubbed, not generalised. This is what the Operation Paperclip use case actually needed. None of the 2026 tools are building this because it doesn't generalise — which is exactly why a solo engineer can own it.

**Blockers to realising this gap:** No proven extraction algorithm, no graph integration, no harness, synthesis pipeline breaks after MCP reconnects.

---

## Cross-domain research sweep — 2026-05-02

A second research pass dispatched 10 parallel agents across fields Wizard had never examined: neuroscience, knowledge management, philosophy of mind, software engineering empirics, information retrieval, organizational learning, economics, AI safety, library science, and complexity science. 20 documents total (10 wild-ideas + 10 cross-domain), ~200 ideas, all grounded in 2023-2026 papers with URLs. Located in `docs/wild-ideas/`.

### What is confirmed true today

**Platform encroachment is not a future risk — it already happened.** GitHub Copilot Memory shipped default-on March 4, 2026, repository-scoped, 28-day hard expiry. OpenAI Codex has `~/.codex/memories/` with background updates. Meta acquired Limitless (ambient capture) December 2025. Mem0 raised $24M Series A, selected by AWS Strands SDK. The competitive window for Wizard's current design is 18-24 months.

**The empirical case is established.** Anthropic's 2026 Agentic Coding Trends Report (actual Claude Code usage data): projects with well-maintained context files produce **40% fewer agent errors and 55% faster task completion**. Gloria Mark's interruption research quantifies $44-90 in recovered labor per session-start reconstruction at standard developer rates.

**Wizard's retrieval baseline is 2020-era.** BM25 alone is consistently beaten by 5-15 nDCG points by hybrid retrieval (BM25 + dense + cross-encoder reranker) across every major benchmark. Nomic Embed v2 and BGE-Reranker run CPU-only and are drop-in upgrades.

**Memory poisoning is a live production threat.** MINJA (NeurIPS 2025, arXiv:2503.03704) achieves >95% injection success rate via query-only interaction. Any externally-ingested content — commit messages, READMEs, API docs — is a live attack vector. OWASP Agentic Top 10 (Dec 2025, endorsed by NIST/Microsoft/NVIDIA) lists memory poisoning as item 6. EU AI Act bulk provisions activate August 2026; California ADMT (disclosure/opt-out for automated decision tools) January 2027.

**Sycophancy amplification is Wizard's silent failure mode.** Without persistent memory each session resets the dynamic. With it, a model that has "learned" an engineer prefers shipping speed over tests will reinforce that belief across all future sessions indefinitely. Documented formally in the 2026 medRxiv structural drift paper.

**The flat note model is being superseded.** Zep/Graphiti (bi-temporal KG): +18.5% accuracy, 90% latency reduction. Kumiho (Mar 2026, arXiv:2603.17244): 93.3% on LoCoMo-Plus via formal AGM belief revision vs 45.7% best prior baseline. MAGMA (Jan 2026, arXiv:2601.03236): four orthogonal graphs (semantic/temporal/causal/entity), 18.6-45.5% improvement, 95% token reduction. The architecture Wizard needs to become already exists in production.

### The idem / ipse problem — the moat is not what we thought

Philosophy of mind surfaced the sharpest challenge. Ricoeur's distinction: **idem** = what was decided (factual record, reproducible from documents). **ipse** = how this person reasons (narrative identity, only observable through longitudinal patterns under pressure, failure, and revision). Every memory system in existence — including Wizard — stores idem. The stated moat ("personal reasoning provenance") requires ipse. They are not the same and current synthesis only achieves the former.

Additionally: automatic synthesis may be **eroding the reasoning capacity Wizard claims to preserve**. The ChatGPT cognitive offloading RCT (d = 0.68 negative effect on retention) and Google Effect meta-analysis (35 studies, 2024) establish this empirically. A system that offloads too much may produce engineers who reason worse over time.

### What doesn't exist yet (the genuine 5-10 year gaps)

**1. Ipse memory** — no system stores how a person reasons, only what they decided. The extraction pipeline required (session transcript → reasoning pattern under constraint) does not exist at research prototype level, let alone production.

**2. The routing layer** — Argote's three-repository model and Wegner's Transactive Memory Systems research both show the same thing: what attrition destroys is the *routing map* (who knows what, how to reach them), not the documents. No AI memory system has built this. The product that builds `{ entity → [sessions that covered it] }` becomes load-bearing team infrastructure.

**3. Prediction-validated memory** — Stanford Generative Agents, Reflexion, TISER (ACL 2025), and predictive coding all converge: memory that makes predictions and checks them against outcomes is qualitatively more useful than memory that only records. No production engineering memory system does this. Minimum viable version: 2-sentence standing prediction at synthesis, checked at next session-start. 30 pairs = enough signal to begin calibration.

**4. Principled forgetting** — YourMemory's formula (`strength = importance × e^(−λ × days) × (1 + recall_count × 0.2)`) achieves ~2× retrieval improvement with two SQLite columns (`last_retrieved_at`, `recall_count`). No production engineering memory system has shipped this. Forgetting is retrieval suppression not data deletion in every biological memory system; Wizard treats all notes as equally retrievable forever.

**5. The BeliefShift benchmark** — there is no longitudinal benchmark for developer memory accuracy across sessions. Whoever builds it owns the evaluation standard for the category.

### What the 10-year picture looks like

Research consensus across economics, SE research, and organizational learning:

- AI handles 60-70% of routine coding volume; humans supervise 50-100 agents each
- The scarcity shifts from memory (solved) to **judgment** — accumulated patterns of *why* under constraint, not *what* was decided
- Memory portability legally regulated analogously to pension portability within 10 years
- The parametric memory limit is real: retrieval as a separate component survives; model weights cannot absorb it (geometric constraint on parametric memory density — proven)
- After ~365 days of use, switching costs exceed annual subscription cost 5-10x; the memory moat becomes structurally permanent (Shapiro/Varian switching cost analysis)

Open questions the research did not resolve:

- Whether automatic synthesis helps or hurts engineers long-term (the evidence points both ways)
- Whether team-scale memory is even possible without destroying epistemic diversity (Artificial Hivemind Effect: uniform context → uniform wrong answers)
- Whether the unit of memory should be a note, a concept, or an emergent cluster (complexity science: emergent cluster; library science: concept node; current Wizard: note)

### Three decisions Wizard must make in the next 90 days

**1. Trust-scoped isolation + `wizard forget` command.** Memory poisoning is live. GDPR enforcement active. ADMT 8 months out. This is no longer optional. All externally-ingested content tagged `trust_level='external'` at ingest. HMAC integrity check on every note before surfacing to model. `wizard forget --session / --task / --before DATE` flags for user lifecycle control.

**2. Retrieval upgrade to hybrid.** BM25 alone is the 2020 baseline. Add Nomic Embed v2 dense vectors + RRF merge + BGE-Reranker cross-encoder + recency decay weighting. Add `last_retrieved_at` and `recall_count` columns to notes table. Implement YourMemory decay formula. Zero new infrastructure required.

**3. Architectural fork: note or concept.** Library science (FRBR work identity, Dublin Core `Relation`/`Coverage`), complexity science (emergent concept clusters, not human artifacts), and KG research (MAGMA, AriGraph episodic-semantic split) all converge: typed concept nodes with provenance edges beat free-text notes with keyword search. The extraction pipeline (transcript → typed triples) is the hard unsolved problem. Deciding whether to solve it determines everything about what Wizard becomes.
