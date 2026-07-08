# Wild Ideas: Continuous Learning & Adaptation for Wizard

> Research scan — May 2026. These are raw ideas extracted from current literature.
> None are commitments. The goal is to map what is possible before deciding what is worth building.

---

## The Core Question

Wizard is currently a passive memory store: notes go in, retrieval brings them out. The question is whether the system could *improve* over time — sharper summaries, fewer stale facts, better retrieval, and genuine adaptation to how a specific engineer thinks — without requiring Wizard to retrain a model or accumulate infinite context.

---

## Idea 1 — ExpeL-Style Experience Extraction (No Parameter Updates Required)

**What it is.** ExpeL (AAAI 2024) shows that an LLM agent can improve its future behaviour by reflecting on past successes and failures as natural language "insights", then injecting those insights into context at inference time. No gradient updates, no fine-tuning. The agent autonomously gathers experiences across tasks, extracts rules ("when the user asks about X, always include Y"), and uses its own successful traces as few-shot examples.

**Wizard application.** After every session, a background pass could compare what Wizard predicted would be useful (notes surfaced via `what_am_i_missing`, `what_should_i_work_on`) against what actually got used or dismissed. Patterns — "this engineer ignores architecture notes but always acts on bug notes" — become first-class retrieval heuristics stored as "meta-notes". No model retraining needed; the rules live in the SQLite store and are injected as system context on the next session.

**Why it matters.** It is the only approach here that works entirely within Wizard's existing architecture (tool calls, SQLite, LLM sampling). The "learning" is fully auditable: you can read the insight notes yourself.

- Paper: [ExpeL: LLM Agents Are Experiential Learners](https://arxiv.org/abs/2308.10144)
- AAAI proceedings: [ACM DL](https://dl.acm.org/doi/10.1609/aaai.v38i17.29936)

---

## Idea 2 — A-Mem: Zettelkasten-Style Agentic Memory Evolution

**What it is.** A-Mem (NeurIPS 2025) builds a memory system inspired by the Zettelkasten note-taking method. When a new memory is added, it does two things automatically: (1) generates links to existing memories that share keywords, context, or patterns; (2) triggers "memory evolution" — existing notes update their own attributes as new experiences provide higher-order context. The system does not use a static schema; it lets structure emerge from content.

**Wizard application.** Right now every Wizard note is a flat record. A-Mem's approach would let notes self-organise: a new note about a bug in the auth service would automatically link to the three previous notes that mention that service, and would prompt a revision of any summary note about auth that has been contradicted. This gives Wizard a graph of interconnected knowledge rather than a bag of independent facts. Stale notes decay or get superseded without manual cleanup.

**Why it matters.** This directly addresses Wizard's biggest current failure: the knowledge graph is implicit. When related notes exist but are never linked, retrieval degrades because semantic search alone cannot surface relationship chains.

- Paper: [A-MEM: Agentic Memory for LLM Agents](https://arxiv.org/abs/2502.12110)
- GitHub: [agiresearch/A-mem](https://github.com/agiresearch/A-mem)

---

## Idea 3 — PAHF: Personalization Loop via Dual Feedback Channels

**What it is.** Meta's PAHF (Personalized Agents from Human Feedback, Feb 2026) introduces a three-step loop for continual personalisation: (1) pre-action clarification — ask a targeted question when intent is ambiguous; (2) memory-grounded action — retrieve and apply stored user preferences before acting; (3) post-action feedback integration — update memory when the user corrects or praises the output. The crucial finding is that both channels matter: pre-action feedback reduces early errors; post-action feedback enables recovery after preference shifts.

**Wizard application.** Two concrete hooks: (a) when `session_start` detects an ambiguous or underspecified context, Wizard could surface one targeted clarifying question ("Last session you were unblocked on auth — should I deprioritise those tasks now?") rather than presenting everything. (b) When `session_end` receives a summary, adding a one-line "was this accurate?" prompt and storing the delta as a preference note would give Wizard a signal about what the engineer values in a summary. Over ten sessions, this would produce a personalised summary style without any model change.

**Why it matters.** This is the only idea in this list that operationalises a feedback loop with real-world validation. Meta tested it on two domains with preference shifts and showed measurable improvement over no-memory and single-channel baselines.

- Paper: [Learning Personalized Agents from Human Feedback](https://arxiv.org/abs/2602.16173)
- GitHub: [facebookresearch/PAHF](https://github.com/facebookresearch/PAHF)

---

## Idea 4 — Agentic Uncertainty Quantification: Knowing What Wizard Doesn't Know

**What it is.** A 2025 research thread on "Agentic Uncertainty Quantification" identifies a specific failure mode called the "Spiral of Hallucination": a minor grounding error early in an agent's reasoning propagates through the context window, biasing all subsequent decisions. Work like UProp and SAUP formally shows how local epistemic uncertainty compounds into global failures. The fix is not eliminating uncertainty but making it visible — agents that know they don't know something can flag it rather than confabulate.

**Wizard application.** Wizard's synthesis step produces summaries that can be wrong: they describe what happened in a session as-of that moment but the underlying facts may have changed. Today there is no staleness signal. A confidence score on each note — decaying with time and number of contradicting subsequent notes — would let Wizard surface "I have three notes about the auth migration but they conflict; here is the newest" rather than silently returning the oldest match. Concretely: a note's confidence could be stored as a column, decayed daily, and reset when a newer note on the same task corroborates it.

**Why it matters.** Memory with no uncertainty model is dangerous for a tool used to make engineering decisions. This does not require LLMs at all: it can be implemented as a scoring function in the repository layer.

- Survey: [Uncertainty Quantification and Confidence Calibration in LLMs](https://arxiv.org/html/2503.15850)
- Position paper: [Agentic Uncertainty Quantification](https://arxiv.org/html/2601.15703)

---

## Idea 5 — Hippocampus-Cortex Dual Memory: Fast Write, Slow Consolidation

**What it is.** The mammalian brain uses two complementary systems: the hippocampus for rapid, episodic encoding of specific events, and the cortex for slow extraction of generalised patterns. A 2024 paper in *Brain Sciences* proposes AI architectures that mirror this: a fast-write store for raw episodic traces and a slow-consolidation process (running offline, during "sleep") that extracts generalised semantic knowledge and writes it back as condensed representations. The hippocampal store is deliberately lossy over time; the cortical store retains only what has been reinforced across multiple episodes.

**Wizard application.** `transcript_raw` is already a fast-write hippocampal store — raw session content before synthesis. The synthesis job is already an approximation of the consolidation phase. What is missing is the *reinforcement* signal: synthesis today does one pass per session, regardless of whether the content overlaps with previous sessions. A "cross-session consolidation" job (schedulable via `wizard vacuum`) could identify notes mentioned in three or more sessions, elevate them to a "cortical" tier with higher retrieval weight, and mark single-mention notes as candidates for pruning. Topics that recur are important; topics that appear once and vanish are probably noise.

**Why it matters.** This gives Wizard a principled basis for the retention/pruning decision it currently has no mechanism for. Notes accumulate indefinitely today; a hippocampus-cortex model provides the theory for deciding what to keep.

- Paper: [Neuroplasticity Meets AI: A Hippocampus-Inspired Approach](https://www.mdpi.com/2076-3425/14/11/1111)
- Synaptic consolidation survey: [Theories of synaptic memory consolidation for continual learning](https://arxiv.org/html/2405.16922v2)

---

## Idea 6 — GEPA / TextGrad: Prompts as Organisms That Evolve

**What it is.** GEPA (Databricks/UC Berkeley, ICLR 2026 Oral) treats prompts as organisms undergoing natural selection: sample execution trajectories, reflect on failures in natural language to diagnose what went wrong, and propose prompt mutations. TextGrad (Stanford, Nature 2024) extends automatic differentiation to text: an LLM provides "textual gradients" — natural language feedback — that propagate backward through a compound AI system to improve individual components. Both systems improve prompts without touching model weights.

**Wizard application.** Wizard's synthesis prompt is fixed. If synthesis quality were evaluated on a proxy signal — does the engineer open tasks mentioned in the synthesis? does the summary match what they said in the next session start? — then GEPA-style reflection could propose mutations to the synthesis prompt over time. "This engineer's synthesis notes keep missing the blocking reason on tasks; add a blocking-reason extraction step." The prompt itself becomes a living artefact that improves with each session, personalised to this engineer's communication style.

**Why it matters.** This is the most speculative idea here, but it is also the only one that could improve Wizard's *reasoning quality* rather than just its data organisation. The risk is prompt drift and reduced predictability, so any implementation would need a rollback mechanism and a human-readable changelog of prompt mutations.

- GEPA: described in [Self-Improving AI Systems (2026)](https://www.morphllm.com/self-improving-ai)
- TextGrad: [Multi-Agent Design: Optimizing Agents with Better Prompts](https://arxiv.org/html/2502.02533v1)
- Prompt optimisation survey: [A Systematic Survey of Automatic Prompt Optimization (EMNLP 2025)](https://aclanthology.org/2025.emnlp-main.1681.pdf)

---

## Idea 7 — Metacognitive Self-Play: Wizard Debates Its Own Summaries

**What it is.** A December 2024 arxiv paper on self-play for non-game agents (arxiv 2512.02731) and a 2025 ICML position paper argue that truly self-improving agents need *intrinsic metacognitive learning*: the ability to evaluate and adapt their own reasoning processes, not just their outputs. The self-play framing: a Generator produces a summary or prediction; a Verifier challenges it; an Updater decides what to change. This is the same GVU topology underlying Constitutional AI, RLHF, and STaR.

**Wizard application.** After synthesis, a second LLM call could play devil's advocate: "List three claims in this synthesis that are likely to be wrong or stale given that the session is now N days old." The challenges are stored as a `contradiction` note type. On the next retrieval, Wizard surfaces both the original note and its challenge. The engineer resolves the contradiction in the next session — generating a ground-truth signal that trains future synthesis quality without any formal reward modelling infrastructure.

**Why it matters.** Wizard's current synthesis is a single forward pass. Adding a cheap adversarial pass costs one extra LLM call per session (at session end, not at retrieval time) and produces a qualitatively different kind of knowledge store: one that is self-auditing.

- Self-play for agents: [Self-Improving AI Agents through Self-Play](https://arxiv.org/abs/2512.02731)
- Metacognitive position paper: [Truly Self-Improving Agents Require Intrinsic Metacognitive Learning](https://openreview.net/forum?id=4KhDd0Ozqe)

---

## Idea 8 — Meta-Learning Agentic Memory Design (Learning to Continually Learn)

**What it is.** A February 2025 paper (arxiv 2602.07755) addresses the fundamental statelesness of foundation models at inference time and proposes meta-learning as the mechanism for determining *how* to organise memory, not just what to store. The key claim: rather than hand-crafting memory operations (write/read/forget), an agent should learn from its own performance history which memory management policies work best for its task distribution.

**Wizard application.** Today Wizard has one retrieval strategy (semantic similarity + recency). A meta-learned memory policy would observe which retrieval strategies produced notes that the engineer actually used and which were ignored, and adjust weighting accordingly. For example, it might discover that for this particular engineer, notes tagged `decision` from more than 30 days ago are almost never useful, while notes tagged `investigation` remain relevant for months. The "learning" is a statistical model over note usage, not a neural network — implementable as a simple logistic regression over note attributes updated nightly.

**Why it matters.** This is the most tractable path to genuine personalisation. It requires no external model, no additional LLM calls, and no schema changes — just logging which notes get surfaced vs. used, and adjusting retrieval weights over time.

- Paper: [Learning to Continually Learn via Meta-learning Agentic Memory Designs](https://arxiv.org/pdf/2602.07755)
- Related: [Learning Personalized Agents from Human Feedback (Meta)](https://ai.meta.com/research/publications/learning-personalized-agents-from-human-feedback/)

---

## Triage: What Is Actually Buildable in Wizard Today

| Idea | Effort | Value | Requires model change? |
|---|---|---|---|
| ExpeL-style insight extraction | Low | High | No |
| Confidence/staleness scores on notes | Low | High | No |
| Hippocampus-cortex cross-session consolidation | Medium | High | No |
| A-Mem note linking on write | Medium | High | No |
| PAHF pre/post-action feedback loop | Medium | High | No |
| Meta-learned retrieval weights | Medium | Medium | No |
| Adversarial synthesis self-play | Low | Medium | No (one extra LLM call) |
| GEPA prompt evolution | High | Medium | No (but operationally complex) |

The top four (ExpeL insight extraction, confidence scores, cross-session consolidation, note auto-linking) are all pure SQLite + retrieval logic changes. None require touching the model, adding external dependencies, or changing the public tool API. They compound: a note graph + staleness scores + cross-session reinforcement gives Wizard a qualitatively different memory model that improves with use rather than merely accumulating data.
