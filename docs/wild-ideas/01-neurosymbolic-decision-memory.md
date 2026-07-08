# Neurosymbolic Decision Memory: Wild Ideas for Wizard

*Blue-sky research — May 2026*

Wizard currently stores notes from coding sessions. This document explores what it could become if we took seriously the question of *why* decisions were made — not just recording events, but building a memory architecture that preserves causal reasoning, supports counterfactual replay, and connects symbolic structure with neural retrieval.

---

## Idea 1: ReasoningBank — Distilling Strategy from Success and Failure

**What it is**

Google Cloud AI Research's ReasoningBank (arXiv:2509.25140, ICLR 2026) is a memory framework that doesn't store raw transcripts or task logs — it distills *generalizable reasoning strategies* from both successful and failed agent runs. Each memory entry has a structured title (core strategy), a brief description, and distilled content: reasoning steps, decision rationales, and operational insights extracted across many past experiences. Crucially, unlike systems that only learn from successes, ReasoningBank actively mines failed trajectories for counterfactual signals — "here's what we tried, why it didn't work, and what should be avoided."

Paired with a technique called Memory-Aware Test-Time Scaling (MaTTS), agents generate multiple distinct reasoning trajectories for the same query, self-contrast them, and synthesize higher-quality memory entries. Results: +34.2% relative effectiveness gains and 16% fewer interaction steps on software-engineering benchmarks.

**Why it's wild**

Most memory systems are passive logs. ReasoningBank is an active distillation process that turns raw experience — including failure — into compressed, reusable strategy. It's closer to how expert engineers develop judgment: not by remembering every bug, but by extracting heuristics from patterns across many bugs.

**How it could apply to Wizard**

Today Wizard saves notes at the end of tasks. A ReasoningBank-style layer would run after each session and ask: "What reasoning patterns appeared here? What decisions were made, and which of those generalise?" Rather than retrieving raw notes, future sessions would retrieve *strategies* — e.g., "When the SQLite schema has no index on `session_id`, query performance degrades; always check explain query plan first." Failed task branches (where the engineer tried approach A, abandoned it, and went with B) become the most valuable training signal.

**Sources**
- https://arxiv.org/abs/2509.25140
- https://research.google/blog/reasoningbank-enabling-agents-to-learn-from-experience/
- https://www.marktechpost.com/2026/04/23/google-cloud-ai-research-introduces-reasoningbank-a-memory-framework-that-distills-reasoning-strategies-from-agent-successes-and-failures/

---

## Idea 2: Bi-Temporal Knowledge Graphs — Memory That Knows When It Learned What

**What it is**

Zep (arXiv:2501.13956, 2025) builds a temporally-aware dynamic knowledge graph G = (N, E, φ) with three hierarchical subgraphs: an episode subgraph (raw non-lossy event logs), a semantic entity subgraph (extracted entities and relationships), and a community subgraph (clusters of related knowledge). The key innovation is a *bi-temporal model*: two separate timelines — one for when events happened chronologically, one for when Zep ingested the information. This means the system can distinguish "I learned on Tuesday that this decision was made last Friday" from "this decision was made on Friday." Graphiti, the underlying engine, supports real-time incremental updates, edge invalidation when facts change, and temporal decay of stale relationships.

**Why it's wild**

Standard databases conflate event time with record time. A bi-temporal graph can answer questions like: "What did I believe about this architecture decision last month, even if I've since revised it?" This is the memory equivalent of version control — not just history, but *history of understanding*.

**How it could apply to Wizard**

Wizard's SQLite schema is append-only but has no temporal reasoning layer. A bi-temporal graph would let Wizard answer: "When did we first consider migrating away from SQLite?", "What was the state of our understanding of the synthesis pipeline in January?", "At what point did we abandon the inline-scrubbing approach?" Each note would be a node; each revision of a belief would be a new edge with temporal metadata, not an overwrite. The graph could surface when an engineer's mental model of a system shifted, which is often more valuable than what the current model is.

**Sources**
- https://arxiv.org/abs/2501.13956
- https://github.com/getzep/graphiti
- https://neo4j.com/blog/developer/graphiti-knowledge-graph-memory/

---

## Idea 3: Agent Trace — Code Context Graphs as Living Decision Provenance

**What it is**

Agent Trace is an open specification (RFC, January 2026) co-developed by Cognition AI and Cursor, with backing from Vercel, Cloudflare, Google Jules, Amp, and OpenCode. It introduces a JSON-based "trace record" that connects code ranges — specific files and line numbers — to the conversations and reasoning chains that produced them. Every commit or file range can carry metadata: who authored it (human, AI, mixed), which conversation produced it, what reasoning iterations occurred. The spec is deliberately minimal: storage is left open (local files, git notes, database). The vision is that future coding agents won't start from zero — they'll retrieve the *decision context* that produced a given code path before modifying it.

The related PROV-AGENT paper (arXiv:2508.02866, IEEE e-Science 2025) extends W3C PROV to cover agent interactions in agentic workflows, capturing prompts, responses, and decisions as first-class provenance nodes using the Model Context Protocol (MCP).

**Why it's wild**

Git records *what* changed. Agent Trace records *why* — the causal chain of reasoning, iterations, and decisions that produced the change. In a world where AI agents write 50%+ of code, "who wrote this?" becomes less useful than "what was the reasoning that produced this?" This is architectural decision records (ADRs) automated and attached to every line of code.

**How it could apply to Wizard**

Wizard is already an MCP server. It could become the Agent Trace store for a codebase — every note, investigation, and decision record gets linked to the code it concerns. When Claude Code opens a file, Wizard could surface the decision chain that led to its current form: "This function was refactored from 3 to 1 DB call in session X because of the N+1 issue found in session Y, after approach Z was tried and abandoned in session W." This is the difference between a note-taking tool and a *decision provenance system*.

**Sources**
- https://cognition.ai/blog/agent-trace
- https://github.com/cursor/agent-trace
- https://arxiv.org/abs/2508.02866

---

## Idea 4: Hindsight Memory — Four-Network Architecture with Belief Revision

**What it is**

"Hindsight is 20/20" (arXiv:2512.12818) proposes a memory architecture that organises agent knowledge into four logical networks rather than a single undifferentiated store:

1. **World network** — objective facts about the external environment
2. **Experience network** — the agent's own past actions and outcomes
3. **Opinion network** — subjective beliefs with *confidence scores* that update as evidence accumulates
4. **Observation network** — preference-neutral summaries of entities synthesised from underlying facts

The three operations are *retain* (incrementally turning streams into structured memory), *recall* (multi-strategy search across networks), and *reflect* (reasoning over the bank to produce answers and update beliefs in a traceable way). The Opinion network is the genuinely novel part: beliefs are not stored as facts but as probability-weighted claims that can be revised without destroying the original evidence. On LongMemEval, this architecture lifts accuracy from 39% to 83.6% using an open-source 20B model — beating GPT-4o on full context.

**Why it's wild**

Most memory systems conflate facts with beliefs. Hindsight separates them, allowing the agent to reason: "I believed the auth service was stateless (confidence 0.7), but new evidence suggests otherwise (confidence 0.3 now)." The old belief and its evidence are preserved; only the weighting changes. This is *defeasible reasoning* with a memory substrate.

**How it could apply to Wizard**

Wizard's notes are currently undifferentiated strings. A four-network structure would let it distinguish: raw observations from a session ("the migration took 4 seconds"), factual conclusions ("the migration is slow because of full-table scans"), and revisable beliefs ("I think we should switch to PostgreSQL — confidence: medium"). When a later session revises a belief, the old confidence and reasoning are archived, not lost. An engineer could query: "What have I changed my mind about in the last three months? What drove those belief revisions?"

**Sources**
- https://arxiv.org/abs/2512.12818
- https://huggingface.co/papers/2512.12818

---

## Idea 5: CLAUSE — Neuro-Symbolic Knowledge Graph Reasoning with Resource Budgets

**What it is**

CLAUSE (arXiv:2509.21035, 2025) is a three-agent neuro-symbolic framework that treats context retrieval as a *sequential decision process* over a knowledge graph. Three specialised agents coordinate: a Subgraph Architect (decides which nodes to expand), a Path Navigator (follows or backtracks reasoning paths), and a Context Curator (selects which evidence to keep). They are jointly optimised using a Lagrangian-constrained multi-agent reinforcement learning algorithm (LC-MAPPO) that enforces per-query *resource budgets* — constraining edge expansions, interaction steps, and selected tokens simultaneously. The result: contexts are compact, provenance-preserving, and deliver predictable performance under deployment constraints. On MetaQA-2-hop, CLAUSE achieves +39.3 EM@1 over GraphRAG with 18.6% lower latency.

**Why it's wild**

The neurosymbolic dimension is genuine: neural agents navigate a symbolic graph, and the symbolic graph structure constrains what the neural agents can hallucinate. Resource budgets encoded in the optimisation objective mean the system is *explicitly reasoning about the cost of reasoning* — a metacognitive capacity almost no current memory system has.

**How it could apply to Wizard**

Wizard's search today is vector similarity. A CLAUSE-style approach would build a knowledge graph of decisions, files, tasks, and engineering entities, then use constrained multi-hop traversal to answer queries like "What decisions do I need to understand before touching the synthesis pipeline?" The graph traversal would surface decision provenance paths (task A → decision B → file C → bug D) rather than semantically similar notes. The resource budget idea is particularly relevant for a personal tool: expensive multi-hop graph searches should only trigger when the query warrants it.

**Sources**
- https://arxiv.org/abs/2509.21035
- https://arxiv.org/abs/2502.03283 (SymAgent, related work)

---

## Idea 6: A-MEM — Zettelkasten-Style Dynamic Memory Networks

**What it is**

A-MEM (arXiv:2502.12110, NeurIPS 2025) applies the Zettelkasten note-taking philosophy to agent memory. Every new memory is stored not just as a text chunk but as a structured note with contextual descriptions, keywords, tags, and *dynamic links* to existing memories based on semantic and structural similarity. Unlike static RAG systems, A-MEM continuously re-analyses the memory repository to establish and revise connections as new memories arrive. The memory network evolves; links that were weak become strong as corroborating evidence accumulates, and previously unconnected memories get linked when a bridging concept appears. On multi-hop reasoning benchmarks, A-MEM achieves at least 2x better performance than MemGPT.

**Why it's wild**

The Zettelkasten insight is that the connections between notes are more valuable than the notes themselves. A-MEM operationalises this for AI agents: the memory isn't a list, it's a growing network of inter-referential knowledge where the structure *is* the reasoning substrate. This is closer to how expert knowledge actually works — not as isolated facts, but as a web of mutually supporting and qualifying claims.

**How it could apply to Wizard**

Each Wizard note currently has a type (investigation, decision, docs, learnings) and a task ID. A-MEM-style linking would mean that when a new decision note is saved, Wizard automatically finds and links it to prior investigations that informed it, prior decisions it supersedes, and future notes that reference the same files or concepts. Over time, the note graph would reveal the *reasoning topology* of the codebase: which clusters of decisions are densely interconnected (stable, well-understood subsystems) vs. sparse (poorly understood, high-risk areas).

**Sources**
- https://arxiv.org/abs/2502.12110
- https://github.com/WujiangXu/A-mem
- https://neurips.cc/virtual/2025/poster/119020

---

## Idea 7: World Models as Internal Simulators — "Dream Before You Code"

**What it is**

World models (David Ha & Jürgen Schmidhuber's foundational work, now extended extensively in 2025) give agents an *internal simulation engine* that can roll forward hypothetical trajectories before taking real-world actions. Recent work ("Current Agents Fail to Leverage World Model as Tool for Foresight", arXiv:2601.03905) documents that current LLM agents systematically underuse their implicit world models — they answer based on pattern-matching rather than simulating consequences. The framing in "Agentic World Modeling: Foundations, Capabilities, Laws, and Beyond" (arXiv:2604.22748) proposes that the next generation of agents will maintain a *compressed causal model of their environment* — not just "what happened" but "what happens when I do X in state Y."

Cognee's blog post "Agent Memory: From Decision Traces to Predictive World Models" (2025) makes the practical argument: decision traces explain the past, but a world model built from those traces lets the agent *anticipate outcomes before committing to them*. The world model is continuously validated against real behaviour through a critic loop.

**Why it's wild**

A memory system that builds a predictive world model doesn't just answer "what did I do before?" — it answers "what will happen if I do this now?" For software engineering, this means an agent that has seen an engineer introduce a migration without a rollback and watched the incident unfold could *simulate* the risk of a proposed change before it's made, drawing on its causal model of the system.

**How it could apply to Wizard**

Wizard's notes already capture investigations, decisions, and outcomes. If those notes were structured as causal traces (decision X in context Y led to outcome Z), Wizard could build a lightweight world model of the codebase's dynamics: "changes to the synthesis pipeline tend to cause cascade failures in session_end within 2 sessions." This world model could surface *pre-flight warnings* when the engineer starts a task similar to a past failure trajectory. It's the difference between a retrospective journal and a prospective risk model.

**Sources**
- https://arxiv.org/html/2601.03905
- https://arxiv.org/html/2604.22748v1
- https://www.cognee.ai/blog/deep-dives/context-graphs-world-models-and-behavioral-validation
- https://worldmodels.github.io/

---

## Idea 8: Causal AI and the Do-Calculus — From Correlation to Intervention Memory

**What it is**

Judea Pearl's do-calculus formalises a fundamental distinction: observing that X is true is not the same as *intervening* to make X true. Causal AI (now becoming industrially viable in 2025-2026 per theCUBE Research and S&P Global analyses) applies this to decision systems. Google DeepMind proved mathematically in 2024 that "any agent capable of adapting to a sufficiently large set of distributional shifts must have learned a causal model" — implying that causal structure is not optional for generalising agents, it's necessary. Causal Reinforcement Learning (crl.causalai.net) extends this to policy learning: agents learn not just what correlates with reward, but what *causes* it, enabling genuine counterfactual ("what if I had done X instead?") and interventional ("if I force X, what will happen?") reasoning.

The key types of causal memory queries: (1) association — "What typically happens after a breaking migration?"; (2) intervention — "If I introduce a feature flag here, what is the predicted impact?"; (3) counterfactual — "If I had used a transactions wrapper in session 42, would the data corruption have occurred?"

**Why it's wild**

Almost all current AI memory is associative: retrieve things similar to the current query. Causal memory is fundamentally different: it lets an agent reason about *hypothetical interventions* — what would have happened under different choices. For a software engineer, this is the difference between a search tool and a reasoning partner that can evaluate trade-offs.

**How it could apply to Wizard**

Wizard could build a causal graph of engineering decisions: nodes are decisions, files, bugs, and performance outcomes; edges carry causal direction (not just correlation). Over enough sessions, Wizard accumulates enough structure to answer: "Given that I'm about to make change X, what is the probability of outcome Y based on past causal patterns?" or "In retrospect, which decision in this task chain most likely caused the regression?" This is the endgame of decision provenance: not a log, but a *causal model of your own engineering practice*.

**Sources**
- https://causalens.com/
- https://crl.causalai.net/
- https://en.wikipedia.org/wiki/Causal_AI
- https://thecuberesearch.com/why-causal-ai-decision-intelligence-2026/
- https://dl.acm.org/doi/10.1145/3665494

---

## Connecting Thread: From Log to Reasoning Substrate

The ideas above share a common trajectory. Current Wizard is at Level 0: unstructured notes stored and retrieved by similarity. The research frontier points toward:

| Level | What is stored | What can be retrieved | What can be reasoned |
|-------|---------------|----------------------|---------------------|
| 0 (now) | Text notes | Similar notes | Nothing — human does this |
| 1 | Structured notes + links (A-MEM) | Related notes via graph traversal | Topology of understanding |
| 2 | Bi-temporal graph + provenance (Zep, Agent Trace) | Decisions and their chains | What was believed when |
| 3 | Belief networks with confidence (Hindsight) | Revisable claims with evidence | What changed my mind |
| 4 | Distilled strategies from success/failure (ReasoningBank) | Generalised heuristics | Pattern-level judgment |
| 5 | Causal world model (Do-Calculus, World Models) | Interventional predictions | What will happen if |

Wizard has a realistic path from Level 0 to Level 2 without radical architecture changes — the MCP protocol, SQLite schema, and note taxonomy are already structurally compatible. Levels 3-5 require investment in a graph layer and a distillation pipeline, but none of the ideas above require capabilities that don't exist today.

---

---

## 2026 Addenda — Second Research Pass

**ActMem — Counterfactual Causal Retrieval** ([arXiv 2603.00026](https://arxiv.org/abs/2603.00026)): Transforms session history into a causal-semantic KG and uses counterfactual probes at retrieval time — surfaces causally-upstream notes even when they are months old and semantically distant. Applied to Wizard: `session_start` retrieves notes that *caused* the current state, not just notes that *mention* current topics.

**ACT-R Activation Decay applied to agent memory** ([arXiv 2505.05083](https://arxiv.org/abs/2505.05083), ACM HAI 2025): Notes have activation levels that decay with time and grow with each reference. Spreading activation automatically boosts associated notes. Requires only two new SQLite columns: `reference_count` and `last_referenced_at`. Replaces recency-ranking with activation-score ranking.

**MemR³ — Reflective Retrieval Loop** ([arXiv 2512.20237](https://arxiv.org/abs/2512.20237)): Router cycles retrieve → reflect → answer with an evidence-gap tracker. Makes `what_am_i_missing` an iterative loop that explicitly tracks "what do I know vs. what is still unresolved" — maps directly to the `mental_model` field surfacing gaps rather than summaries.

**Minimal viable upgrade combining all three:** AriGraph's `semantic_facts` table (storage reform) + ACT-R activation decay column (retrieval reform) + MemR³ reflective loop in `what_am_i_missing` (reasoning reform). All SQLite schema changes + Python logic — no new infrastructure.

*Research conducted May 2026. All papers are publicly accessible at the URLs listed.*
