# Wild Ideas: Knowledge Graphs & Personal Ontologies for Software Engineers

> Research synthesis — May 2026. These are ideas worth stealing.

Wizard currently stores flat notes. Text retrieval finds what you wrote; it
cannot reason about what you know. This document explores what a truly
structured, semantically rich personal knowledge system could look like for a
software engineer — the weird academic stuff, not the Obsidian tutorials.

---

## Idea 1: The PKG API — Your Knowledge Graph as a First-Class Data Primitive

**The research:** The University of Stavanger group published the [PKG API](https://arxiv.org/html/2402.07540) at
ACM Web Conference 2024, paired with a longer [ecosystem survey in the Journal of
Web Semantics](https://www.sciencedirect.com/science/article/pii/S2666651024000044). Their
definition is precise: a PKG is a machine-readable graph owned and controlled
by one individual, built for personalized computation — not a subset of a
public knowledge base.

**The wild part:** They formalise provenance on every triple using the PAV
ontology (`pav:createdBy`, `pav:authoredOn`), GDPR-style erasure, and
per-triple access control via RDF ACL. The API accepts natural-language
statements and converts them to RDF triples on the fly.

**Applied to Wizard:** Instead of free-text notes, every observation Wizard
captures — "the auth service timeouts in staging after 3 pm", "Elena owns
the API gateway", "we chose Postgres over MySQL in March because of JSONB
support" — is stored as a typed, provenance-stamped triple. You get full
SPARQL queries, not just BM25 keyword search. You can ask: *"What decisions
did I make while working on the payments service in Q1 that touched the DB
layer?"* and get a precise answer.

---

## Idea 2: Temporal Knowledge Graphs — Knowledge That Knows When It Was True

**The research:** The 2024 survey [A Survey on Temporal Knowledge Graph:
Representation Learning and Applications](https://arxiv.org/abs/2403.04782)
covers the full landscape. The core model: quadruples `(head, relation, tail,
timestamp)` instead of triples. The key research split is between
*interpolation* (fill in missing knowledge within a time range using
historical data) and *extrapolation* (predict what will be true in the future
based on evolution patterns).

The [RE-GCN paper at SIGIR 2021](https://dl.acm.org/doi/10.1145/3404835.3462963)
built a recurrent graph convolution network over timestamped KG snapshots —
modelling how entity relationships *evolve* structurally over time, not just
what they are at a point in time. More recent 2025 work in Springer Machine
Learning and Cybernetics ([Temporal KG representation with complex
evolution](https://link.springer.com/article/10.1007/s13042-025-02625-w))
combines periodic patterns with sequential evolution.

**Applied to Wizard:** Wizard knows that you worked on the payments service
last year. But it does not know that your mental model of that service is now
stale — that the architecture changed six months ago and your cached
understanding is wrong. A temporal KG makes *belief timestamps* explicit. A
node like `payments-service hasOwner Elena` carries `validFrom: 2024-01
validTo: 2024-09`. Wizard can surface: *"You have 14 facts about the auth
subsystem that haven't been confirmed in over 90 days — some may be outdated."*
This is proactive knowledge decay management, not just retrieval.

---

## Idea 3: Event-Centric Knowledge Graphs — Your Work as a Causal Narrative

**The research:** The [ChronoGrapher system (2025, Semantic Web
Journal)](https://www.semantic-web-journal.net/content/chronographer-event-centric-knowledge-graph-construction-informed-graph-traversal)
builds event-centric KGs via informed graph traversal, treating events as
first-class nodes with causal and temporal edges to other events and entities.
The [IEEE TKDE Event Knowledge Graph survey](https://dl.acm.org/doi/10.1109/TKDE.2022.3180362)
establishes the vocabulary: events have participants, triggers, outcomes, and
causal successors.

The key insight is that entities (a service, a person, a ticket) are
*secondary* — events (a decision, an outage, a deploy, a code review) are the
primary structure of work. [Narrative Graph (Springer JSSSE
2023)](https://link.springer.com/article/10.1007/s11518-023-5561-0) builds
on this to generate coherent stories from event chains.

**Applied to Wizard:** Current Wizard stores notes about entities. An
event-centric Wizard stores *what happened and why*. The graph might look like:

```
IncidentEvent(2025-03-14) --causedBy--> DeployEvent(2025-03-13)
DeployEvent --triggeredBy--> TicketJIRA-1234
IncidentEvent --resolvedBy--> Hotfix(commit:abc123)
Hotfix --authoredBy--> Person(Kiran)
Hotfix --informedBy--> Note("Elena mentioned rate-limit bug in standup 2025-03-10")
```

You can now ask causal questions: *"What upstream event led to the auth
regression I fixed last sprint?"* — and the graph can answer.

---

## Idea 4: Neurosymbolic Reasoning Over Personal Graphs — Beyond Retrieval Into Inference

**The research:** The [Neurosymbolic AI for Reasoning over Knowledge Graphs
survey (IEEE TKDE 2024)](https://ieeexplore.ieee.org/iel8/5962385/6104215/10603423.pdf)
and its accompanying [IOS Press Handbook on Neurosymbolic AI and Knowledge
Graphs](https://ebooks.iospress.nl/volume/handbook-on-neurosymbolic-ai-and-knowledge-graphs)
map three categories of approach: (1) logically-informed embedding approaches,
(2) embedding approaches with logical constraints, and (3) rule learning over
KGs.

The 2025 paper [On the Potential of Logic and Reasoning in Neurosymbolic
Systems Using OWL-Based KGs (Sage
2025)](https://journals.sagepub.com/doi/10.1177/29498732251320043) highlights
the underexplored power of OWL-based graphs specifically: if your ontology
asserts that `AuthService isA MicroService` and `MicroService hasRisk
VendorLockIn`, a reasoner can *infer* that `AuthService hasRisk VendorLockIn`
— without you ever writing that fact down.

**Applied to Wizard:** The gap between current RAG (find similar text) and
what engineers actually need (reason about knowledge) is enormous. With an
OWL-backed personal ontology, Wizard could:

- Infer that a tech debt note about `PaymentsService` applies to
  `SubscriptionService` if the ontology asserts they share the same underlying
  `BillingCore` module.
- Apply transitivity: if Elena owns the API gateway and the API gateway owns
  the rate-limit config, infer Elena is the right person to ask about rate
  limits — even if you never wrote that down.
- Detect contradictions: two notes asserting different owners for the same
  service trigger an inconsistency warning.

This is not LLM generation — it is formal logical inference over a graph you
own. Deterministic, auditable, fast.

---

## Idea 5: Knowledge Graph Embeddings for Personal Context Retrieval — GNN as Memory Index

**The research:** The broader KG-embedding-for-recommendation literature
(surveyed in [KGIE, ScienceDirect
2024](https://www.sciencedirect.com/science/article/abs/pii/S0950705124004477)
and the [Stanford CS224W GNN-RAG analysis](https://medium.com/stanford-cs224w/enhancements-to-graph-neural-retrieval-for-knowledge-graph-reasoning-870675ac458d))
has established that GNNs trained over heterogeneous graphs find paths between
entities that pure vector similarity misses — because they traverse *relation
types*, not just semantic closeness.

The 2025 [Knowledge Graph-Guided RAG (arxiv
2502.06864)](https://arxiv.org/html/2502.06864v1) combines dense vector
retrieval (DPR) for unstructured text *and* a GNN for structural path retrieval
over the graph, fusing both signals via path-attention mechanisms.

**Applied to Wizard:** Today Wizard's search is pure BM25 over note text. A
personal KG embedding layer would let you ask: *"What notes are connected to
the PaymentsService via at most 2 hops, where one hop is a 'decision' edge?"*
— pulling in notes you'd never find by keyword. An engineer asking about a bug
in the checkout flow would surface not just notes about that service, but also
the architectural decision three months ago that constrained the design of that
flow, and the person who made it. The GNN traverses the personal graph; the
LLM synthesises the answer.

---

## Idea 6: Biological Memory Decay Applied to a Knowledge Graph — Forgetting as a Feature

**The research:** Ebbinghaus's forgetting curve is well-established. What is
novel is applying it to a knowledge graph rather than isolated facts. A 2025
[Hacker News thread on AI memory with biological decay](https://news.ycombinator.com/item?id=47914367)
describes a system that assigns each memory node a `strength` score; every
retrieval reinforces and flattens the decay curve, while unretrieved nodes
decay toward a pruning threshold. Recent work on [Human-like Forgetting Curves
in Deep Neural Networks (arxiv 2506.12034)](https://arxiv.org/html/2506.12034v2)
shows that neural nets can be trained to reproduce Ebbinghaus dynamics.

In spaced-repetition research, SuperMemo and RemNote have validated that
review scheduling based on retrieval strength dramatically outperforms static
archives for long-term retention.

**Applied to Wizard:** Instead of an ever-growing flat archive, each node in
the personal KG has a `confidence` score that decays over time. Decay rate
depends on node type: a decision node about a long-lived service decays slowly;
a meeting note about a transient sprint issue decays fast. When `confidence`
drops below a threshold, Wizard proactively surfaces the node:
*"You captured this architectural constraint 8 months ago and haven't revisited
it. Still accurate?"* The engineer confirms or revises — which re-strengthens
the node and potentially propagates updates to connected nodes (a change to a
core constraint ripples to all nodes that cite it). The KG becomes a living
structure, not a write-once archive.

---

## Idea 7: The SWEBOK Ontology as a Structural Vocabulary for Engineer Knowledge

**The research:** The IEEE Software Engineering Body of Knowledge has been
formalised into an OWL ontology — see [Engineering the Ontology for the
SWEBOK (Springer)](https://link.springer.com/chapter/10.1007/3-540-34518-3_3)
and [Software Engineering Ontology: A Development Methodology (Abran et
al.)](http://s3.amazonaws.com/publicationslist.org/data/a.abran/ref-2121/839.pdf).
The ontology defines ten Knowledge Areas (Requirements, Design, Testing, etc.)
as OWL classes, with subclass hierarchies and cross-domain relations. The SPEM
ontology (Software Process Engineering Metamodel) extends this with process and
method concepts.

**Applied to Wizard:** An engineer's personal knowledge graph could use SWEBOK
concepts as its upper ontology — the shared vocabulary from which personal
instances hang. Instead of a note tagged `#architecture`, you have an instance
of `SoftwareDesign:ArchitecturalDecision` linked to a `Requirements:UserNeed`
and a `Testing:TestStrategy`. This means:

- Notes are structured against a shared conceptual framework, not freeform tags
- Cross-engineer knowledge can eventually be merged (two engineers' PKGs using
  the same ontology are interoperable)
- An LLM prompted with the ontology schema can extract structured facts from
  raw session transcripts automatically, placing them in the right SWEBOK
  category

The ontology gives Wizard's extraction pipeline a target schema rather than
free-form synthesis.

---

## Idea 8: Code Knowledge Graphs as the Missing Link Between Code and Context

**The research:** A wave of 2024–2025 papers has built semantic KGs from
repository structure. [SemanticForge (arxiv
2511.07584)](https://arxiv.org/html/2511.07584) builds a KG from AST, CFG, and
DFG to support repository-level code generation. [Code Graph Model (arxiv
2505.16901)](https://arxiv.org/pdf/2505.16901) integrates a repository code
graph into the LLM attention mechanism directly, achieving 43% resolution on
SWE-bench Lite. [Codebase-Memory (arxiv 2603.27277)](https://arxiv.org/html/2603.27277v1)
uses Tree-sitter to build persistent KGs from any repo, exposed via MCP.

The [GraphCoder paper (ASE
2024)](https://dl.acm.org/doi/10.1145/3691620.3695054) builds Code Context
Graphs for completion. The key insight from all of these: code structure is a
natural graph — functions call functions, modules import modules, types
implement interfaces — and representing this explicitly beats chunked text
retrieval for reasoning tasks.

**Applied to Wizard:** Wizard today captures knowledge *about* code in
prose notes. A richer design would ingest the repo's code KG alongside the
engineer's personal KG, creating a *heterogeneous* graph that spans:

- Code nodes: `Function`, `Module`, `Interface`, `Service`
- Personal nodes: `Decision`, `Incident`, `Person`, `Meeting`
- Cross-layer edges: `Function wasChangedBy Decision`, `Incident triggeredInModule Module`

An engineer asking "why is this function so complex?" could traverse from the
code node, through the `wasChangedBy` edge, to the ADR that constrained it,
to the meeting where that decision was made. Code archaeology as a graph query.

---

## Idea 9: Heterogeneous Personal KG — Merging the Professional Self

**The research:** The broader [Emergent Mind overview on Personal Knowledge
Graphs](https://www.emergentmind.com/topics/personal-knowledge-graphs-pkgs)
and the [Cognee ontology-AI memory integration
post](https://www.cognee.ai/blog/deep-dives/ontology-ai-memory) describe the
direction: a personal KG that unifies heterogeneous node types — not just
notes, but calendar events, code commits, Jira tickets, Slack threads — into
a single traversable graph with typed edges.

The [Brain Cache paper (CHI 2025 GenAI
Workshop)](https://generativeaiandhci.github.io/papers/2025/genaichi2025_51.pdf)
frames this as a *cognitive exoskeleton*: externalising biological memory into
semantic networks that can be activated through contextual interaction. The
[Gradual Cognitive Externalization framework (arxiv
2604.04387)](https://arxiv.org/html/2604.04387v1) models how ambient AI
systems can progressively absorb cognitive load from humans — and the key
enabler is structured representation, not flat logs.

**Applied to Wizard:** The engineer's full professional graph would contain:

| Node Type | Example |
|---|---|
| `Decision` | "Chose Postgres over MySQL — 2024-03" |
| `Incident` | "Auth timeout incident — 2025-03-14" |
| `Person` | "Elena — owns API gateway" |
| `Ticket` | "JIRA-1234 — rate limit bug" |
| `Meeting` | "Sprint retro 2025-03-15" |
| `Commit` | "abc123 — hotfix for rate limit" |
| `Service` | "PaymentsService" |
| `Concept` | "Circuit breaker pattern" |

Every edge is typed and timestamped. The graph can answer questions no flat
search engine can: *"What technical concepts did I rely on most heavily during
the months I was oncall?"* or *"Which people and tickets were involved in every
incident this year that touched the auth layer?"* This is not retrieval. It is
graph traversal over a structured model of your professional life.

---

## Connecting Thread

All nine ideas converge on the same gap: Wizard captures *text* when it should
be capturing *structured knowledge*. The transition looks like this:

```
Today:    session text  →  synthesis prose  →  BM25 keyword search
Future:   session text  →  KG extraction   →  typed triples + temporal stamps
                                            →  OWL inference
                                            →  GNN traversal
                                            →  decay-aware proactive surfacing
```

The engineering challenge is not the graph query layer — it is the extraction
pipeline that converts messy session transcripts into clean, typed graph
triples. That is the hard problem worth solving next.

---

## 2026 Addenda — Key Discoveries Not in Original Research Pass

### Zep / Graphiti — Production-Ready Temporal Agent Memory Graph

**The research:** [Zep: A Temporal Knowledge Graph Architecture for Agent Memory](https://arxiv.org/abs/2501.13956) (arXiv 2501.13956, Jan 2025) + [Graphiti GitHub](https://github.com/getzep/graphiti). MIT-licensed, production-ready. Three-tier graph: episode nodes (raw observations) → semantic entity nodes (extracted triples) → community subgraphs. Bi-temporal model: valid time (when true in world) + transaction time (when Wizard learned it). Triple-fusion search: cosine + BM25 + BFS graph traversal. Outperforms MemGPT by 18.5% accuracy at 90% lower latency.

**Why it matters for Wizard:** This is the most directly applicable architecture found. Replacing Wizard's flat BM25 search with Graphiti's three-tier graph would give bi-temporal queries ("what did I believe about auth in January?"), automatic entity extraction from session transcripts, and semantic deduplication. It's already an MCP-compatible backend.

---

### MAGMA — Four Orthogonal Memory Graphs

**The research:** [MAGMA: A Multi-Graph based Agentic Memory Architecture](https://arxiv.org/abs/2601.03236) (arXiv 2601.03236, Jan 2026). Deconstructs memory into four separate graphs: Semantic (concept relationships), Temporal (when things happened), Causal (what caused what), Entity (people, systems, files). Query type determines which graph is traversed. Outperforms baselines on LoCoMo and LongMemEval; 18.6–45.5% improvement over flat-vector retrieval; 95% token reduction.

**Why it matters for Wizard:** Today all four relationship types are entangled in flat BM25 — a causal query ("what caused this regression?") and a semantic query ("what do I know about Redis?") go through the same index. MAGMA's architecture is the argument for why the separation matters.

---

### AriGraph / PersonalAI — Episodic-Semantic Split with Full Provenance

**The research:** [AriGraph: Learning Knowledge Graph World Models with Episodic Memory](https://arxiv.org/abs/2407.04363) (arXiv 2407.04363, 2024) + [PersonalAI: Systematic Comparison of KG Storage and Retrieval](https://arxiv.org/abs/2506.17001) (arXiv 2506.17001, 2025). AriGraph unifies episodic (raw observations with provenance edges) and semantic (extracted triples) memory. PersonalAI extends with hyper-edges for multi-party relationships and pluggable traversal strategies (A*, WaterCircles, BeamSearch).

**Why it matters for Wizard:** The episodic-semantic split means every semantic fact is traceable back to the session that generated it. Today a Wizard note has no such link. The hyper-edge model handles the "three agents, one codebase" multi-party case from the stress test.

---

## Source References

- [PKG API: A Tool for Personal Knowledge Graph Management (arxiv 2402.07540)](https://arxiv.org/html/2402.07540)
- [An Ecosystem for Personal Knowledge Graphs: A Survey and Research Roadmap (ScienceDirect 2024)](https://www.sciencedirect.com/science/article/pii/S2666651024000044)
- [A Survey on Temporal Knowledge Graph: Representation Learning and Applications (arxiv 2403.04782)](https://arxiv.org/abs/2403.04782)
- [Temporal KG Reasoning via Evolutional Representation Learning (SIGIR 2021)](https://dl.acm.org/doi/10.1145/3404835.3462963)
- [Temporal KG Representation with Complex Evolution (Springer 2025)](https://link.springer.com/article/10.1007/s13042-025-02625-w)
- [ChronoGrapher: Event-Centric KG Construction (Semantic Web Journal 2025)](https://www.semantic-web-journal.net/content/chronographer-event-centric-knowledge-graph-construction-informed-graph-traversal)
- [Event-Centric Temporal KG Construction: A Survey (MDPI Mathematics 2023)](https://www.mdpi.com/2227-7390/11/23/4852)
- [What is Event Knowledge Graph: A Survey (IEEE TKDE 2022)](https://dl.acm.org/doi/10.1109/TKDE.2022.3180362)
- [Neurosymbolic AI for Reasoning over KGs: A Survey (IEEE TKDE 2024)](https://ieeexplore.ieee.org/iel8/5962385/6104215/10603423.pdf)
- [On the Potential of Logic and Reasoning in Neurosymbolic Systems Using OWL-Based KGs (Sage 2025)](https://journals.sagepub.com/doi/10.1177/29498732251320043)
- [Knowledge Graph-Guided Retrieval Augmented Generation (arxiv 2502.06864)](https://arxiv.org/html/2502.06864v1)
- [KGIE: KG Convolutional Network for Recommender System (ScienceDirect 2024)](https://www.sciencedirect.com/science/article/abs/pii/S0950705124004477)
- [Stanford CS224W: Enhancements to GNN Retrieval for KG Reasoning](https://medium.com/stanford-cs224w/enhancements-to-graph-neural-retrieval-for-knowledge-graph-reasoning-870675ac458d)
- [Engineering the Ontology for the SWEBOK (Springer)](https://link.springer.com/chapter/10.1007/3-540-34518-3_3)
- [Software Engineering Ontology: A Development Methodology (Abran et al.)](http://s3.amazonaws.com/publicationslist.org/data/a.abran/ref-2121/839.pdf)
- [SemanticForge: Repository-Level Code Generation via Semantic KGs (arxiv 2511.07584)](https://arxiv.org/html/2511.07584)
- [Code Graph Model (arxiv 2505.16901)](https://arxiv.org/pdf/2505.16901)
- [Codebase-Memory: Tree-Sitter-Based KGs via MCP (arxiv 2603.27277)](https://arxiv.org/html/2603.27277v1)
- [GraphCoder: Repository-Level Code Completion via Code Context Graph (ASE 2024)](https://dl.acm.org/doi/10.1145/3691620.3695054)
- [Brain Cache: Generative AI as a Cognitive Exoskeleton (CHI 2025 GenAI Workshop)](https://generativeaiandhci.github.io/papers/2025/genaichi2025_51.pdf)
- [Gradual Cognitive Externalization Framework (arxiv 2604.04387)](https://arxiv.org/html/2604.04387v1)
- [Human-like Forgetting Curves in Deep Neural Networks (arxiv 2506.12034)](https://arxiv.org/html/2506.12034v2)
- [AI Memory with Biological Decay — Hacker News Discussion](https://news.ycombinator.com/item?id=47914367)
- [Application of Knowledge Graph in Software Engineering: A Systematic Literature Review (ScienceDirect 2023)](https://www.sciencedirect.com/science/article/abs/pii/S0950584923001829)
- [Personal Knowledge Graphs Overview (Emergent Mind)](https://www.emergentmind.com/topics/personal-knowledge-graphs-pkgs)
- [Cognee: Enhancing KGs with Ontology Integration](https://www.cognee.ai/blog/deep-dives/ontology-ai-memory)
- [Zettelkasten: The Emergent Power of a Web of Notes with Links (Stimpunks 2024)](https://stimpunks.org/2024/08/24/the-emergent-power-of-a-web-of-notes-with-links/)
