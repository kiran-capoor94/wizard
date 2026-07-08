# Wild Ideas: Temporal Reasoning and Time-Aware Memory

> How a memory system could understand not just *what is true* but *what was true when, and why it changed.*

---

## Motivation

Wizard stores notes from coding sessions. But code, constraints, and understanding evolve. A decision captured three months ago may now be actively harmful — the constraint it worked around has been lifted, the library it chose has been superseded, the risk it hedged has materialised. A note that says "we use X because of Y" is only useful if the system knows whether Y is still true.

The current model treats memory as a snapshot. The ideas below treat memory as a timeline.

---

## Idea 1: Bitemporal Knowledge Graphs — Two Clocks, Not One

**The core insight:** Every fact has two independent timestamps, not one. *Valid time* is when the fact was true in the world. *Transaction time* is when the system learned the fact. These are different, and conflating them is what makes most memory systems wrong under update.

**What the research shows:** The Zep paper (Jan 2025) implements this directly. Each edge in their knowledge graph carries `valid_at` and `invalid_at` (world-time) and a separate `created_at` / `expired_at` (system-time). When a new fact contradicts an existing one, the old edge gets `invalid_at` stamped rather than deleted. This means you can query "what did the system believe was true on 2024-11-01, as of what the system knew at that point?" — a question that ordinary vector stores cannot answer.

The Memento system (Apr 2026) applied this to agent memory and scored 92.4% task-averaged on LongMemEval, with no catastrophic category failures — compared to 41.1% for the markdown baseline. The worst Memento category was still 86.5%. The key differentiator was exactly this: temporal invalidation rather than overwrite.

**Applied to Wizard:** Notes about architectural decisions could carry a `valid_from` / `valid_until` rather than just `created_at`. A note saying "we pin boto3 to <1.28 because of the S3 presign regression" could be automatically superseded when a later note records the pin being removed. Queries like `search("why do we pin boto3")` would surface the supersession chain, not just the oldest match.

**Sources:**
- [Zep: A Temporal Knowledge Graph Architecture for Agent Memory (arxiv 2501.13956)](https://arxiv.org/abs/2501.13956)
- [Building a Bitemporal Knowledge Graph for LLM Agent Memory: A 92% LongMemEval Case Study](https://explore.n1n.ai/blog/building-bitemporal-knowledge-graph-llm-agent-memory-longmemeval-2026-04-11)
- [Graphiti on GitHub (getzep/graphiti)](https://github.com/getzep/graphiti)
- [Graphiti on Neo4j blog](https://neo4j.com/blog/developer/graphiti-knowledge-graph-memory/)

---

## Idea 2: Knowledge as Event Stream — Source the Facts, Not Just the State

**The core insight:** Event sourcing (Fowler, CQRS canon) says never store current state — store the sequence of events that produced it. Current state is a derived projection. This is radical when applied to knowledge: your beliefs are not facts, they are the current projection of all the evidence you have consumed so far.

**What the research shows:** AxonIQ (2024) articulated why event sourcing is "the missing memory layer for enterprise AI." Every change to agent knowledge is stored as an immutable, sequential event: `NoteAdded`, `BeliefInvalidated`, `ConstraintLifted`, `DecisionSuperseded`. The knowledge graph is a materialised view over this log. You can replay the log to reconstruct exactly what the agent believed at any prior point. You can audit why a belief exists by inspecting the event chain that created it.

Kurrent (formerly EventStoreDB) is positioning itself explicitly as an event-native database for agentic AI for exactly this reason.

**Applied to Wizard:** Today, `save_note` writes a row. Under event sourcing, it appends an event. The note content is the same, but now you can ask: "replay all events up to 2024-09-15 and show me what the system believed about the auth layer." This is the difference between a diary and a version-controlled repo.

**Sources:**
- [AI Agent Explainability: Why Your Infrastructure Needs to Remember (AxonIQ)](https://www.axoniq.io/blog/ai-agent-explainability-event-sourcing-infrastructure)
- [Event Sourcing Pattern (Martin Fowler)](https://martinfowler.com/eaaDev/EventSourcing.html)
- [Enterprise Guide to Implementing Event Sourcing Agents (SparkCo)](https://sparkco.ai/blog/enterprise-guide-to-implementing-event-sourcing-agents)
- [Kurrent: Event-Native Database](https://www.kurrent.io/)

---

## Idea 3: Belief Revision — Treating Contradiction as Signal, Not Error

**The core insight:** In formal AI (going back to AGM theory, 1985), *belief revision* is the process of rationally updating a belief set when new evidence contradicts it. The three operations are: expansion (add a new belief), contraction (remove a belief without adding its opposite), and revision (add a belief that contradicts existing ones, then repair the set). The interesting one for memory systems is revision — it requires determining which prior beliefs to drop to maintain consistency.

**What the research shows:** An EMNLP 2024 study benchmarked ~30 LLMs on belief revision using the Belief-R dataset. The finding was damning: LLMs generally struggle to appropriately revise beliefs in response to new information. Models that update readily tend to over-update (sycophantic capitulation) while models that resist updating exhibit rigidity even when the new evidence is unambiguous. Neither is correct.

The right model is the AGM postulates: a revision should be *minimal* (discard as little prior belief as possible), *consistent* (the result should not contain a contradiction), and *faithful* (prioritise newer evidence over older when forced to choose). Kumiho (arxiv 2603.17244, March 2026) is the first system to formally *prove* satisfaction of the AGM postulates and Hansson's belief base postulates in a live memory architecture. Its property graph uses immutable revision nodes, mutable tag pointers, and typed dependency edges — a memory that cannot just store facts but can reason about which prior fact a new fact displaces, and why. On LoCoMo-Plus, Kumiho achieves 93.3% judge accuracy vs the best prior baseline of 45.7% — a gap that cannot be explained by retrieval quality alone.

BeliefShift (arxiv 2603.23848, March 2026) is the first benchmark designed specifically to test whether long-running agents handle *opinion drift* correctly over multi-session trajectories. Its 2,400 interaction trajectories spanning 10–50 sessions found a hard trade-off: models that personalise aggressively resist drift poorly; factually grounded models miss legitimate updates. Neither knows what the other knows. The four BeliefShift metrics — Belief Revision Accuracy (BRA), Drift Coherence Score (DCS), Contradiction Resolution Rate (CRR), and Evidence Sensitivity Index (ESI) — are the clearest operationalisation yet of what "temporal belief consistency" means in practice.

**Applied to Wizard:** When a new note contradicts an existing one (e.g., "we removed the Redis cache" contradicts "we use Redis for session state"), the system should not silently coexist with both. It should flag the contradiction, timestamp the supersession, and retain the old belief with a `superseded_at` marker. The agent querying memory gets the current belief plus provenance of what it replaced. Kumiho's AGM correspondence gives Wizard a precise specification for what "correct" revision looks like — not just a heuristic.

**Sources:**
- [Belief Revision: The Adaptability of Large Language Models Reasoning (EMNLP 2024)](https://aclanthology.org/2024.emnlp-main.586/)
- [How Should Rational Belief Revision Work in LLMs? (OpenReview)](https://openreview.net/pdf?id=LRf19n5Ly3)
- [Belief Revision (Wikipedia — good primer on AGM)](https://en.wikipedia.org/wiki/Belief_revision)
- [Kumiho: Graph-Native Cognitive Memory with Formal Belief Revision Semantics (arxiv 2603.17244)](https://arxiv.org/abs/2603.17244)
- [BeliefShift: Benchmarking Temporal Belief Consistency and Opinion Drift in LLM Agents (arxiv 2603.23848)](https://arxiv.org/abs/2603.23848)

---

## Idea 4: The Ebbinghaus Curve Applied to Agent Memory — Strategic Forgetting

**The core insight:** Human memory decays predictably. Ebbinghaus (1885) showed that without reinforcement, ~70% of a memory is lost within 24 hours, but each successful retrieval resets the curve and slows future decay. This is exploited by spaced-repetition systems (Anki, SuperMemo). The wild idea: apply the same curve to agent memory — facts that haven't been accessed or reinforced in a long time should have their retrieval weight reduced, not because they're wrong, but because they're likely stale.

**What the research shows:** The SAGE framework (arxiv 2409.00872, published in Neurocomputing 2025) is the most direct application. SAGE's "MemorySyntax" method combines the Ebbinghaus forgetting curve with linguistic knowledge to assign decay weights to memories. Memories that are frequently retrieved stay sharp; memories that are never accessed decay toward archival status. The result was a 2.26× improvement on closed-source models.

Separately, the FOREVER paper (arxiv 2601.03938, 2026) applies forgetting-curve-inspired replay schedules to continual learning in language models, reducing catastrophic forgetting by 24%.

The most direct implementation evidence is YourMemory (GitHub: sachitrafa/YourMemory, 2025–2026) — an MCP memory server that applies Ebbinghaus decay with an explicit formula: `strength = importance × e^(−λ_eff × days) × (1 + recall_count × 0.2)`, where `λ_eff = 0.16 × (1 − importance × 0.8)`. Memories below strength 0.05 are automatically pruned. Benchmarked on LoCoMo (200 QA pairs, 10 multi-month conversations), YourMemory achieves 52% Recall@5 — nearly doubling the industry average — and reduces token waste by 84%. It requires zero infrastructure (DuckDB only), making it a direct analogue to Wizard's SQLite-first design. The Hacker News thread (2026) generated 200+ comments, signalling strong practitioner interest in this exact trade-off.

**Applied to Wizard:** A note saved 18 months ago about a now-unused AWS service should rank lower in retrieval than a note from last week, even if both match the query vector. More usefully: notes that have never been retrieved since creation could be flagged as "cold" and surfaced for review — the system proactively asking "this constraint was recorded 6 months ago; is it still true?" This inverts the usual forgetting curve: instead of forgetting silently, the system surfaces stale memories for active confirmation. YourMemory's formula is directly portable — Wizard already has `created_at`; it just needs `last_retrieved_at` and `recall_count`.

**Sources:**
- [SAGE: Self-evolving Agents with Reflective and Memory-augmented Abilities (arxiv 2409.00872)](https://arxiv.org/abs/2409.00872)
- [FOREVER: Forgetting Curve-Inspired Memory Replay for Language Model Continual Learning (arxiv 2601.03938)](https://arxiv.org/html/2601.03938v1)
- [Is there a better way to forget? Modelling memory decay in deep knowledge tracing (ScienceDirect 2025)](https://www.sciencedirect.com/science/article/pii/S0950705125019227)
- [YourMemory: Ebbinghaus forgetting curve for MCP memory (GitHub sachitrafa/YourMemory)](https://github.com/sachitrafa/YourMemory)
- [Show HN: AI memory with biological decay (52% recall) — Hacker News](https://news.ycombinator.com/item?id=47914367)

---

## Idea 5: Graph Reification and Provenance — Facts That Know Their Own History

**The core insight:** Graph reification is the practice of making a statement about a statement. Instead of `(Redis, used_for, sessions)`, you store `(claim_42: Redis used_for sessions, asserted_by: session_2024-03-12, confidence: 0.9, source: backend-notes)`. The edge itself becomes a node you can query. This enables provenance tracking: where did this belief come from, who asserted it, under what conditions, with what confidence?

**What the research shows:** TrustGraph (2024-2025) has built graph reification into its core architecture for AI agents. Each fact carries metadata: who said it, when, with what confidence, under what conditions. The Zep paper implements a version of this through its "communities" abstraction — groups of related facts share provenance metadata that lets the system understand when and why a belief cluster was formed.

The Semantica framework on GitHub (Hawksight-AI) extends this further: every node in the semantic layer carries an audit trail, enabling agents to distinguish "I know this because the user told me last week" from "I inferred this from pattern matching against old notes."

**Applied to Wizard:** Currently, all notes are equally credible. Under reification, a note saved during an active coding session (high confidence, fresh context) would outrank a note synthesised from a transcript (derived, potentially compressed). A note explicitly tagged as a `decision` would outrank an `investigation` note when the question is "what approach did we choose." The system wouldn't just retrieve facts — it would reason about the epistemic status of each fact before surfacing it.

**Sources:**
- [Graph Reification (TrustGraph)](https://trustgraph.ai/guides/key-concepts/graph-reification/)
- [Semantica: Semantic layers with explainability and provenance (Hawksight-AI/semantica)](https://github.com/Hawksight-AI/semantica)
- [Zep architecture paper — communities and provenance](https://arxiv.org/html/2501.13956v1)

---

## Idea 6: Reflexion and Temporal Meta-Cognition — Agents That Learn From Their Own Past Mistakes

**The core insight:** The Reflexion framework (Shinn et al., NeurIPS 2023) showed that agents can dramatically improve by reflecting on their own failures and storing those reflections as episodic memory. Crucially, the reflection is *temporal*: "on trial 3, I did X because I believed Y, but Y was false, and doing X caused failure Z." This is not just error correction — it is a structured history of the agent's own epistemic growth.

**What the research shows:** Reflexion achieved 91% pass@1 on HumanEval (vs GPT-4's 80%) without any fine-tuning, purely through iterative self-reflection stored as episodic memory. The key is that reflections are not just corrections — they are causally linked to the prior belief that produced the error. This creates a temporal chain: original_belief → action → outcome → reflection → revised_belief.

Meta-Policy Reflexion (arxiv 2509.03990, 2025) extended this to extract *reusable rules* from reflections, not just episode-specific corrections. A reflection about a specific mistake becomes a generalised policy: "whenever I see pattern P in a Python codebase, avoid approach A because of constraint C."

**Applied to Wizard:** Today, synthesis produces notes about what happened. A Reflexion-style layer would additionally record: "the note saved on 2024-08-15 predicted the cache would be the bottleneck; the note saved on 2024-09-02 records that the bottleneck was actually the DB write path." The system could surface this as a learning: "prediction about cache performance was wrong; actual bottleneck was DB writes." Over time, these calibrations would build a model of where past reasoning went wrong — and that model would be queryable.

**Sources:**
- [Reflexion: Language Agents with Verbal Reinforcement Learning (arxiv 2303.11366)](https://arxiv.org/abs/2303.11366)
- [Meta-Policy Reflexion: Reusable Reflective Memory and Rule Admissibility (arxiv 2509.03990)](https://arxiv.org/html/2509.03990v1)
- [How Do Agents Learn from Their Own Mistakes? (HuggingFace / Turing Post)](https://huggingface.co/blog/Kseniase/reflection)

---

## Idea 7: Architecture Decision Records as a Living Temporal Graph

**The core insight:** The ADR (Architecture Decision Record) practice encodes decisions as structured documents with explicit status transitions: `proposed → accepted → superseded`. Each ADR that supersedes another creates an explicit temporal edge: "this decision replaced that one, at this time, for this reason." This is a hand-curated temporal knowledge graph already in wide use — the insight is to make it queryable by an agent.

**What the research shows:** The ADR ecosystem has formalised the lifecycle: Initiating → Researching → Evaluating → Implementing → Maintaining → Sunsetting. The key principle is that accepted ADRs are never *edited* — they are *superseded*, which creates an immutable chain. As of 2024, the Azure Well-Architected Framework mandates ADRs. Agents are now being built to auto-generate ADRs by scanning codebases (Nov 2025 work by Strengholt). A PROFES 2025 study tracked the temporal evolution of architectural complexity and technical debt in microservices, demonstrating that the *rate of change* of architectural decisions is itself a signal — projects where ADRs accumulate and are never superseded show higher technical debt.

The wild extension: if Wizard ingests ADRs as structured notes with their supersession links, the agent can answer "what was the authentication strategy in Q1 2024 and what changed it?" by traversing the supersession graph rather than doing unstructured retrieval.

**Applied to Wizard:** Sessions that touch architectural decisions could automatically emit lightweight ADR-style facts: `(decision: use Redis for sessions, valid_from: 2024-03-10, status: superseded, superseded_by: note_782, superseded_at: 2024-09-15)`. This is not a new tool — it is a schema on top of existing notes.

**Sources:**
- [Architecture Decision Records (adr.github.io)](https://adr.github.io/)
- [Building an Architecture Decision Record Writer Agent (Piethein Strengholt, Medium)](https://piethein.medium.com/building-an-architecture-decision-record-writer-agent-a74f8f739271)
- [ADR bliki (Martin Fowler)](https://martinfowler.com/bliki/ArchitectureDecisionRecord.html)
- [Temporal Evolution of Architectural Complexity and Technical Debt in Microservices (PROFES 2025)](https://conf.researchr.org/details/profes-2025/profes-2025-research-papers/18/Temporal-Evolution-of-Architectural-Complexity-and-Technical-Debt-in-Microservices-A)

---

## Idea 8: The TIME Benchmark — What Temporal Failure Looks Like in Practice

**The core insight:** There are now dedicated benchmarks that stress-test temporal reasoning in LLMs. Their failure modes reveal exactly where a naive memory system would break — and therefore what a time-aware system must get right.

**What the research shows:** The TIME benchmark (NeurIPS 2025) contains 38,522 QA pairs across 11 sub-tasks at three levels of temporal complexity, covering intensive temporal information, fast-changing event dynamics, and complex temporal dependencies. "Test of Time" (arxiv 2406.09170, NeurIPS 2024) found that LLMs remain susceptible to temporal reasoning errors even when temporal context is explicitly provided.

LongMemEval (arxiv 2410.10813) specifically tests *multi-session temporal questions* — and finds that accuracy collapses to below 50% on these. The failure mode is consistent: models retrieve the most semantically similar past fact without checking whether it has been superseded. "The cache is our main bottleneck" scores high semantic similarity against "what is the main bottleneck?" even if 15 subsequent sessions have made that fact obsolete.

A separate benchmark, LiveFact (arxiv 2604.04815, 2026), tests whether LLMs can detect *temporal staleness* in knowledge — whether they recognise that a fact that was true in 2023 may not be true in 2026. Base models outperform instruction-tuned models on this task, suggesting that RLHF-style training actively degrades temporal reasoning by rewarding confident-sounding answers over temporally calibrated ones.

**Applied to Wizard:** The LongMemEval failure mode is precisely Wizard's risk. A note from 6 months ago about "why we chose Postgres over DynamoDB" should not be treated as equally current as a note from last week. The fix is not a better retrieval model — it is explicit temporal metadata that the retrieval layer can filter on.

**Sources:**
- [TIME: A Multi-level Benchmark for Temporal Reasoning of LLMs (NeurIPS 2025, HuggingFace)](https://huggingface.co/papers/2505.12891)
- [Test of Time: A Benchmark for Evaluating LLMs on Temporal Reasoning (arxiv 2406.09170)](https://arxiv.org/abs/2406.09170)
- [LongMemEval Benchmark (arxiv 2410.10813)](https://arxiv.org/pdf/2410.10813)
- [LiveFact: A Dynamic, Time-Aware Benchmark for LLM-Driven Fake News Detection (arxiv 2604.04815)](https://arxiv.org/html/2604.04815v2)
- [Time Awareness in Large Language Models: Benchmarking Fact Recall Across Time (arxiv 2409.13338)](https://arxiv.org/abs/2409.13338)

---

## Idea 9: Timeline Self-Reflection and Adaptive Temporal Reasoning — Agents That Know What They Know *When*

**The core insight:** The failure mode of most memory systems is not wrong facts — it is temporally unanchored facts. An agent that knows "the cache was the bottleneck" without knowing *when* that was true, and *what changed after*, is not reasoning — it is pattern-matching against a static snapshot. Two 2025–2026 research threads address this from opposite directions: TISER builds explicit temporal timelines at inference time; AdapTime adapts its reasoning *strategy* based on the temporal type of the question.

**What the research shows:**

TISER (Amazon Science, ACL 2025, arxiv 2504.05258) decomposes temporal reasoning into four stages: initial reasoning trace, extraction of salient temporal events into an explicit timeline, self-reflection to detect inconsistencies between the reasoning trace and the timeline, and final answer generation. The self-reflection stage is the key novelty — the model constructs a timeline as a structured object, then audits its own reasoning for temporal contradictions before committing to an answer. On temporal QA benchmarks, TISER enabled Qwen2.5-7B fine-tuned on GPT-4-generated data to score 91.1% macro average EM — surpassing GPT-4o's 78.5% baseline. The insight is that *explicit timeline construction forces temporal consistency*; without it, models reason fluently about time while violating basic temporal constraints (event A happened before event B, but the model uses B's outcome to explain A).

AdapTime (ACL 2026 Findings, arxiv 2604.24175) takes a different angle: not all temporal questions require the same reasoning strategy. Simple questions (when did X happen?) need reformulation; multi-hop questions (what was the state of X during the period when Y was also true?) need rewriting and review. AdapTime's LLM planner dynamically selects which stages to execute based on semantic characteristics of the question and the model's confidence in intermediate steps, outperforming fixed-pipeline CoT on complex temporal tasks while adding negligible overhead on simple ones. The underlying finding is wild: *temporal questions require qualitatively different reasoning depending on whether they involve absolute timestamps, relative intervals, or causal ordering* — and no fixed prompt handles all three.

**Applied to Wizard:** When a user asks `search("why did we drop Celery")`, that is a temporal causal query — it requires locating notes in the right temporal sequence, checking whether the reason cited in the earliest note was revisited in later notes, and understanding whether the decision was final or tentative. A TISER-style approach would: (1) retrieve candidate notes, (2) construct an explicit timeline of the decision process, (3) reflect on whether the timeline is internally consistent, and (4) surface the conclusion with temporal anchoring ("as of session 2024-09-12, the decision was final"). AdapTime's insight suggests that Wizard should detect whether a query is a point-in-time lookup, a range query, or a causal chain query — and apply different retrieval and reasoning strategies accordingly.

**Sources:**
- [TISER: Learning to Reason Over Time — Timeline Self-Reflection for Improved Temporal Reasoning (ACL 2025, arxiv 2504.05258)](https://arxiv.org/abs/2504.05258)
- [TISER GitHub (amazon-science/TISER)](https://github.com/amazon-science/TISER)
- [AdapTime: Enabling Adaptive Temporal Reasoning in Large Language Models (ACL 2026 Findings, arxiv 2604.24175)](https://arxiv.org/abs/2604.24175)
- [Beyond Dialogue Time: Temporal Semantic Memory for Personalized LLM Agents (arxiv 2601.07468)](https://arxiv.org/html/2601.07468v1)

---

## Cross-Cutting Theme: The Minimal Viable Upgrade

All nine ideas point at the same minimal change that would make Wizard genuinely time-aware without a rewrite:

1. Add `valid_from` / `valid_until` to notes (bitemporal, Idea 1).
2. When synthesis produces a note that contradicts an existing note, stamp the old note `superseded_at` rather than leaving both untouched (Belief Revision / AGM, Idea 3).
3. Track `last_retrieved_at` and `recall_count` per note so retrieval can down-weight stale facts using YourMemory's Ebbinghaus formula (Idea 4).
4. Surface notes that haven't been retrieved or confirmed in >90 days as candidates for staleness review (strategic forgetting, Idea 4).
5. Record the *source* of each note — session transcript, explicit save, synthesis derivation — as provenance metadata (Reification, Idea 5).
6. When answering temporal causal queries, construct an explicit timeline of candidate notes before generating the answer, then self-check for internal temporal inconsistencies (TISER, Idea 9).

That is five columns on the `notes` table, one staleness-surfacing query, and one temporal self-check step in the `search` tool. Everything else — the knowledge graph, ADR traversal, Reflexion-style growth tracking, AGM-formal revision — follows naturally from having the temporal primitives in place.

The 2026 research makes one additional thing clear: the right test harness for a time-aware Wizard is a BeliefShift-style longitudinal benchmark — multi-session interaction trajectories where the engineer's beliefs about the codebase genuinely change, and the system is scored on whether it tracks those changes correctly rather than anchoring to stale notes. No such benchmark exists for developer memory systems yet. Building one would be the most valuable empirical contribution Wizard could make to the field.
