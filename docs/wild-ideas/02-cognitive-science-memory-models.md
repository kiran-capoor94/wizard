# Cognitive Science Memory Models: Wild Ideas for Wizard

Research sweep across cognitive science, neuroscience, and psychology for ideas that could
radically change how an AI agent memory system like Wizard is designed.

---

## 1. Baddeley's Multicomponent Working Memory — the Central Executive Gap

**What it is**

Alan Baddeley's 50-year-old model splits working memory into four components: a phonological
loop (rehearsing verbal/acoustic information), a visuospatial sketchpad (holding visual
scenes), an episodic buffer (a limited-capacity workspace that binds information from the
other components *plus* long-term memory into a coherent episode), and a central executive
(the attentional supervisor that decides what gets processed). The 2025 retrospective update
in *Quarterly Journal of Experimental Psychology* confirms the model still holds across
neuroimaging, patient lesion, and dual-task studies.

**Why it is surprising**

Every AI agent memory design I've read treats the context window as a monolithic "working
memory." Baddeley says that's wrong — even the brain maintains *modality-specific* scratch
pads that are processed in parallel and fused later. The central executive is not a store at
all; it is a control process that *selects* what gets bound. The model implies that the
limiting resource isn't capacity (7 ± 2 items) — it's *binding bandwidth*.

**How it could apply to Wizard**

- Keep three parallel scratch-pad streams per session: (a) the current task state (what the
  agent is actively doing), (b) a visuospatial analogue (file structure, architecture
  diagrams, dependency graph), (c) a phonological analogue (the most recent N tokens of
  conversation as a rolling verbal rehearsal buffer).
- The "central executive" maps cleanly to the `what_should_i_work_on` routing step — the
  thing that decides which memories are *attended to* right now rather than just retrieved.
- The episodic buffer's binding role is the hardest gap to fill. Current Wizard conflates
  retrieval and binding; separating them would mean: retrieve candidates from multiple
  stores, then run a cheap synthesis step to bind them into a coherent situational model
  before injecting into context.

**Sources**

- [The multicomponent model of working memory fifty years on (Hitch, Allen, Baddeley, 2025)](https://journals.sagepub.com/doi/10.1177/17470218241290909)
- [Empowering Working Memory for Large Language Model Agents (arXiv 2312.17259)](https://arxiv.org/pdf/2312.17259)
- [Cognitive Workspace: Active Memory Management for LLMs (arXiv 2508.13171)](https://www.arxiv.org/pdf/2508.13171)
- [Position: Episodic Memory is the Missing Piece for Long-Term LLM Agents (arXiv 2502.06975)](https://arxiv.org/pdf/2502.06975)

---

## 2. Hippocampal Indexing Theory — Memory as Pointers, Not Copies

**What it is**

Timothy Teyler and Pascal DiScenna proposed in 1986 (updated by Teyler and Rudy in 2007)
that the hippocampus does not *store* episodic memories. It stores only a sparse *index* —
a binding code that points to the distributed cortical representations of each feature of an
experience. When you recall an event, the hippocampus reactivates its index, which in turn
reactivates the cortical fragments, which your brain then re-assembles. The content lives in
cortex. The address book lives in the hippocampus.

**Why it is surprising**

This is a database architecture argument buried in a neuroscience paper from 1986. The brain
does not store memories the way most AI systems store notes: as self-contained text blobs.
It stores a pointer to a reconstruction recipe. The implications for storage efficiency and
for graceful degradation are enormous. Memories stored as pointers to distributed features
are naturally compositional — you can re-use cortical fragments across many episodes without
duplication.

**How it could apply to Wizard**

- Notes in Wizard's SQLite database are currently self-contained blobs. An indexing
  architecture would split each memory into: an index record (task_id, timestamp, semantic
  tags, context hash) and a set of feature records (file path snippets, error messages,
  decisions, entity names). Retrieval reassembles them on demand.
- This would make Wizard's storage dramatically more deduplicatable — the same file path
  appearing in 30 notes isn't stored 30 times; it is referenced by 30 index entries.
- Reconsolidation (section 7 below) becomes natural: you update a feature record, and every
  index that points to it gets the update "for free" at next retrieval.

**Sources**

- [The hippocampal indexing theory and episodic memory: Updating the index (Teyler & Rudy, 2007)](https://pubmed.ncbi.nlm.nih.gov/17696170/)
- [An Integrated Index: Engrams, Place Cells, and Hippocampal Memory (ScienceDirect)](https://www.sciencedirect.com/science/article/pii/S0896627320305286)
- [Hippocampal Engrams and Contextual Memory (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12006847/)

---

## 3. Sleep Consolidation and Hippocampal Replay — The Offline Processing Case

**What it is**

During slow-wave sleep, the hippocampus replays compressed sequences of the day's
experiences (sharp-wave ripples) in coordination with cortical slow oscillations and
thalamic spindles. This hippocampal-to-neocortical dialogue gradually transfers
episodic traces into stable semantic representations. The process is not passive archiving;
it is active *transformation* — details are pruned, patterns are extracted, and redundant
encodings are merged. A 2025 paper in *Physiological Reviews* provides the most
comprehensive review of what is known mechanistically.

**Why it is surprising**

The brain has a *dedicated offline phase* for memory reorganization. It does not try to
consolidate memories while simultaneously experiencing new things — that would cause
catastrophic interference. Yet almost every AI memory system consolidates in real time,
inline, during the session. Nature solved the stability-plasticity dilemma by *separating
online and offline processing in time*, not by making the online system cleverer.

Recent AI work validates this directly: the 2022 Nature Communications paper
"Sleep-like unsupervised replay reduces catastrophic forgetting" showed that a
sleep-inspired replay phase cuts forgetting in ANNs by a statistically significant margin.
NeuroDream (SSRN 2025) reports up to 38% reduction in forgetting with a dedicated "dream
phase." The 2025 arxiv paper "Learning to Forget: Sleep-Inspired Memory Consolidation for
Resolving Proactive Interference in LLMs" shows LLMs themselves suffer proactive
interference (old knowledge bleeding into new task performance) and that a sleep-gated KV
cache achieves 99.5% retrieval accuracy at interference depth 5.

**How it could apply to Wizard**

- Wizard's existing `synthesis` pipeline (triggered on session end) is the right *shape* of
  solution but fires once. A sleep analogue would run a second, heavier consolidation pass
  several hours after the session ends — when the engineer is asleep — using more
  compute to merge related episodic notes into semantic summaries without the
  urgency constraint of an active session.
- The two-pass structure mirrors slow-wave (initial encoding) + REM (emotional/causal
  relabelling) sleep: first pass extracts facts; second pass rewrites the narrative to
  extract *why* things happened.
- Proactive interference in Wizard manifests as stale context bleeding into new sessions.
  The "SleepGate" KV-cache decay paper directly suggests that tagging memories with a
  decay weight and actively evicting stale keys is preferable to ever-growing retrieval
  pools.

**Sources**

- [Sleep-like unsupervised replay reduces catastrophic forgetting in ANNs (Nature Comms, 2022)](https://www.nature.com/articles/s41467-022-34938-7)
- [NeuroDream: A Sleep-Inspired Memory Consolidation Framework (SSRN, 2025)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5377250)
- [Learning to Forget: Sleep-Inspired Consolidation for Proactive Interference in LLMs (arXiv 2025)](https://arxiv.org/html/2603.14517v1)
- [A model of autonomous hippocampus-neocortex interactions driving sleep-dependent consolidation (PNAS)](https://www.pnas.org/doi/10.1073/pnas.2123432119)
- [Sleep's contribution to memory formation (Physiological Reviews, 2024)](https://journals.physiology.org/doi/full/10.1152/physrev.00054.2024)
- [Systems memory consolidation during sleep (PMC, 2025)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12576410/)

---

## 4. Episodic vs. Semantic Memory — The Consolidation Bottleneck

**What it is**

Endel Tulving's 1972 distinction separates episodic memory (specific, context-bound events
with spatiotemporal tagging: "last Tuesday I found the bug in the payment service at 3pm")
from semantic memory (decontextualised facts and knowledge: "the payment service uses
optimistic locking"). Over time, the hippocampus gradually extracts semantic knowledge from
episodic instances — a process called *systems consolidation*. This is lossy by design:
the system discards the episode and keeps the extracted rule.

**Why it is surprising**

The brain's default behaviour is not to remember experiences — it is to *forget experiences
and keep abstractions*. The episodic trace exists primarily as raw material for semantic
extraction, not as a permanent record. This inverts the common AI agent assumption that
episodic logs are the ground truth and summaries are approximations. In the brain, the
summary *is* the goal, and the episode is scaffolding.

A 2025 position paper (arXiv 2502.06975) identifies five properties that make episodic
memory distinct for LLM agents: long-term storage, explicit reasoning, single-shot
learning, instance-specificity, and contextual grounding. It explicitly argues these are
absent from current agent designs and that this gap is the primary barrier to continuity.

**How it could apply to Wizard**

- Wizard currently stores notes (episodic) and synthesises summaries (semantic), but treats
  them symmetrically — both live forever in SQLite with equal weight. The biological
  model says the episodic note should carry an explicit TTL, with the expectation that it
  will be absorbed into a semantic record and then archived (or deleted).
- The `transcript_raw` cleanup already implemented in v2.2.14 is accidentally correct
  biological behaviour. Generalise this: every episodic note should have a `synthesised_at`
  field; once synthesised into a semantic summary, the raw note is moved to cold storage
  rather than kept in hot retrieval.
- Retrieval should distinguish query type: "what happened on Tuesday" → episodic store;
  "how does the payment service work" → semantic store. Routing queries to the wrong store
  is the AI equivalent of confabulation.

**Sources**

- [Episodic Memory for AI Agents: How It Works (Atlan, 2025)](https://atlan.com/know/episodic-memory-ai-agents/)
- [Position: Episodic Memory is the Missing Piece for Long-Term LLM Agents (arXiv 2502.06975)](https://arxiv.org/pdf/2502.06975)
- [A Practical Guide to Memory for Autonomous LLM Agents (Towards Data Science)](https://towardsdatascience.com/a-practical-guide-to-memory-for-autonomous-llm-agents/)
- [Beyond the Bubble: Context-Aware Memory Systems (Tribe AI, 2025)](https://www.tribe.ai/applied-ai/beyond-the-bubble-how-context-aware-memory-systems-are-changing-the-game-in-2025)

---

## 5. Prospective Memory — Remembering to Do, Not Just What Was Done

**What it is**

Prospective memory is the cognitive system responsible for remembering to execute an
*intention at a future moment*. It is distinct from retrospective memory (remembering what
happened). Prospective memory has two sub-types: time-based (remember to do X at 3pm) and
event-based (remember to do X when you next see Y). Neuroimaging shows the dorsal attention
network sustains monitoring for trigger cues, while the default mode network handles
spontaneous retrieval of the intention when a cue is detected. A 2025 Frontiers paper
decodes these neural dynamics with hidden Markov models.

**Why it is surprising**

Almost all AI agent memory research concerns retrospective memory — how to retrieve what has
already happened. Prospective memory is the harder unsolved problem for agents doing real
engineering work. An engineer says "remind me to revisit this when the PR is merged." That
is not a note to retrieve by semantic search; it is a time-and-event-gated intention that
must spontaneously surface. The brain has entirely separate neural machinery for this, and
it is largely absent from current agent architectures.

**How it could apply to Wizard**

- Wizard's tasks are the closest existing analogue, but they require explicit querying. A
  prospective memory layer would monitor session-start events and compare the current
  context (what task is active, what files are open, what PR is in progress) against a set
  of registered trigger-action pairs.
- Event-based triggers: "when this Jira ticket moves to In Review, surface the note about
  the edge case in payment processing." These are structural matches against context state,
  not semantic search.
- The dual-pathway neuroscience (top-down monitoring vs. bottom-up spontaneous retrieval)
  maps to: (a) a background daemon that checks triggers at session start, and (b) an
  inline similarity check that fires when the current context semantically matches a
  registered intention.
- Critical: prospective memory failures in humans are *cue detection failures*, not
  intention storage failures. The intention is intact; the trigger is missed. This implies
  Wizard should invest in richer trigger specification, not better storage.

**Sources**

- [Decoding the neural dynamics of prospective remembering (Frontiers, 2025)](https://www.frontiersin.org/journals/human-neuroscience/articles/10.3389/fnhum.2025.1686657/full)
- [Dual pathways to prospective remembering (Frontiers)](https://www.frontiersin.org/journals/human-neuroscience/articles/10.3389/fnhum.2015.00392/full)
- [Prospective memory — Wikipedia](https://en.wikipedia.org/wiki/Prospective_memory)

---

## 6. The Forgetting Curve and Desirable Difficulty — Strategic Forgetting as a Feature

**What it is**

Hermann Ebbinghaus (1885) showed that memory retention follows an exponential decay curve,
recoverable through spaced repetition. Robert Bjork's later "new theory of disuse" proposes
that memory strength has two orthogonal dimensions: *storage strength* (how deeply
consolidated) and *retrieval strength* (how easily accessible right now). Crucially, Bjork
argues that *reducing retrieval strength* through controlled forgetting forces harder
re-encoding when the memory is later retrieved, which raises storage strength more than
easy, high-retrieval-strength recall would. Difficulty is productive. This is the
"desirable difficulties" research programme.

**Why it is surprising**

The standard engineering intuition is: never lose data. The neuroscience says the opposite
— strategically *lowering* the retrieval probability of non-recently-used memories makes
them *stronger* when next retrieved. A system that gives you everything immediately may
actually impair long-term retention. The YourMemory MCP project applies Ebbinghaus decay
directly and reports +16pp better recall than Mem0 on LoCoMo benchmarks.

**How it could apply to Wizard**

- Every memory in Wizard should carry a retrieval strength score (decaying function of
  time-since-last-access and recency-of-encoding), separate from its storage strength score
  (depth of synthesis, number of times cross-referenced).
- `what_should_i_work_on` and `search` should deliberately *not* surface high-storage /
  low-retrieval memories instantly — instead, surface them at the point of maximum
  productive difficulty (i.e., when they are about to fall below a recall threshold).
- This is not data loss — it is triage. The memory exists; its surfacing probability is
  throttled. This keeps the engineer's working context uncluttered while building deeper
  long-term recall through spaced re-encounter.
- A "memory pressure" metric per task: as retrieval strength decays, the task triggers a
  resurfacing nudge. Engineer reviews, revises the note, and storage strength climbs.

**Sources**

- [YourMemory: Agentic AI memory with Ebbinghaus forgetting curve decay (GitHub)](https://github.com/sachitrafa/YourMemory)
- [Replication and Analysis of Ebbinghaus' Forgetting Curve (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC4492928/)
- [Bjork Learning and Forgetting Lab — desirable difficulties research](https://bjorklab.psych.ucla.edu/research/)
- [Human-like Forgetting Curves in Deep Neural Networks (arXiv, 2025)](https://arxiv.org/html/2506.12034v2)
- [AI, Memorization, and Forgetting through the Ebbinghaus Lens (ResearchGate)](https://www.researchgate.net/publication/391847984_AI_MEMORIZATION_AND_FORGETTING_A_CRITICAL_ANALYSIS_THROUGH_THE_LENS_OF_THE_EBBINGHAUS_CURVE)

---

## 7. Memory Reconsolidation — Every Retrieval is a Rewrite Window

**What it is**

Karim Nader's landmark 2000 experiment showed that retrieving a memory destabilises it — the
memory briefly becomes labile (modifiable) before reconsolidating. During this window, the
memory can be updated with new information, weakened, or strengthened. Reconsolidation
requires protein synthesis in the amygdala and hippocampus; if blocked pharmacologically,
the retrieved memory degrades. This means retrieval is not a read operation — it is a
read-modify-write operation on the biological substrate.

**Why it is surprising**

Current AI memory systems treat retrieval as purely non-destructive. Biological memory says
every access is a mutation opportunity. The brain uses this to keep memories calibrated to
current beliefs. It also means that the act of remembering something in a new context
silently updates the memory. This is a feature: stale beliefs get corrected on retrieval.
It is also a risk: highly retrieved memories can become systematically distorted.

The AI reconsolidation implication was directly studied in ZenBrain (arXiv 2604.23878),
which implements vmPFC-coupled FSRS scheduling with prediction-error signals — the memory
is more strongly updated when the retrieved content *surprises* the model relative to its
current beliefs.

**How it could apply to Wizard**

- When Wizard retrieves a note, it should run a lightweight consistency check: does the
  retrieved content contradict the current session context? If yes, flag it for
  reconsolidation (offer the engineer a one-click update).
- Prediction-error gating: if the retrieved memory is *expected* (matches current context
  well), low-cost retrieval only. If the retrieved memory is *surprising* (low similarity
  to recent context but high relevance), trigger a heavier re-encoding pass that annotates
  it with current context.
- This transforms Wizard's `search` from a passive lookup into an active belief-updating
  moment — each retrieval potentially improves the quality of the stored memory.

**Sources**

- [An update on memory reconsolidation updating (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC5605913/)
- [ZenBrain: Neuroscience-Inspired 7-Layer Memory Architecture (arXiv 2604.23878)](https://arxiv.org/html/2604.23878)
- [Rethinking Memory in AI: Taxonomy, Operations, Topics (arXiv 2505.00675)](https://arxiv.org/html/2505.00675v1)
- [Neural mechanisms of reactivation-induced updating (PNAS)](https://www.pnas.org/doi/10.1073/pnas.1319630110)

---

## 8. Predictive Coding and the Free Energy Principle — Memory as Prediction Error

**What it is**

Karl Friston's free energy principle (2010, *Nature Reviews Neuroscience*) proposes that the
brain's fundamental drive is to minimise *prediction error* — the difference between its
internal generative model of the world and incoming sensory data. Memory, under this
framework, is not a record of what happened; it is a parametric generative model of the
world. Perception is inference. Learning is model updating. Attention is precision-weighting
of prediction errors. The hippocampus encodes high-precision prediction errors — the
surprising parts of experience that the cortical model failed to predict.

**Why it is surprising**

If memory is a generative model rather than a record, the right question is not "what do I
remember?" but "what model of the world am I maintaining, and how much did today's
experiences update it?" The things worth remembering are precisely the things that
*surprised* you — the unexpected exceptions to your model. Everything that matched your
predictions can be discarded; it added no information.

This has a radical implication for agent systems: the highest-value memories to encode and
preserve are the *surprises* — bugs you didn't expect, architectural decisions that
contradicted your mental model, failures of a dependency you thought was reliable. Routine
successful operations are essentially zero-information events; storing them at the same
fidelity as surprises is wasteful.

**How it could apply to Wizard**

- Introduce a *surprise score* at the point of note creation: how much does this note
  deviate from prior session patterns? Notes that confirm known patterns get low-fidelity
  storage. Notes that represent genuine model updates get high-fidelity storage and
  automatic synthesis priority.
- Session synthesis already extracts patterns; the predictive coding lens inverts this: the
  synthesis pipeline should explicitly flag *anomalies* as the highest-value content to
  preserve, not bury them in averaged-out summaries.
- The "what_am_i_missing" tool is the most natural home for this: it should not ask "what
  notes exist?" but "where does my model of this codebase most poorly predict current
  reality?" — then surface the sessions/notes that would update that model.

**Sources**

- [Predictive coding under the free-energy principle (Friston, Royal Society B, 2009)](https://royalsocietypublishing.org/doi/abs/10.1098/rstb.2008.0300)
- [The free-energy principle: a unified brain theory? (Friston, Nature Reviews Neuroscience, 2010)](https://www.nature.com/articles/nrn2787)
- [From Neuroscience to AI: Friston's Free Energy Principle and Active Inference (ResearchGate)](https://www.researchgate.net/publication/397380587_From_Neuroscience_to_Artificial_Intelligence_Karl_Friston's_Free_Energy_Principle_and_the_Rise_of_Active_Inference)

---

## 9. Context-Dependent and State-Dependent Memory — Retrieval Needs the Right Environment

**What it is**

Memory retrieval is dramatically improved when the retrieval context matches the encoding
context. This includes external context (physical environment, visual cues) and internal
state (mood, arousal, even intoxication). Godden and Baddeley's 1975 classic: divers who
learned word lists underwater recalled them better underwater than on land. The encoding
specificity principle (Tulving): what gets stored is not just the item but its context, and
retrieval cues must overlap with encoded contextual features to work.

**Why it is surprising**

Current vector-similarity retrieval in AI memory systems operates purely on semantic content
of the query versus stored text. It is entirely context-blind. Biological retrieval uses
context as a primary cue — the state you're in when you try to remember something
fundamentally determines what surfaces. For an engineer memory tool, this suggests that
*who you are right now* (what task you're on, what files are open, what recent errors you've
encountered) is a better retrieval key than *what you type into a search box*.

**How it could apply to Wizard**

- Every retrieval in Wizard should be context-enriched before the similarity search: the
  current session's task, the active Jira ticket, the most recently modified files, and
  the most recent error messages should all be implicit retrieval cues, not just the
  explicit query.
- Session-start personalisation already partially does this. Extend it: build a
  "context fingerprint" for each session and use it to bias retrieval scores — notes
  encoded during similar context fingerprints get a relevance boost.
- State-dependent retrieval implies Wizard should track *what mode the engineer was in*
  when notes were created (debugging, architecting, reviewing, implementing) and match
  retrieval mode to encoding mode for maximum recall.

**Sources**

- [Context-Dependent Memory — ScienceDirect overview](https://www.sciencedirect.com/topics/neuroscience/context-dependent-memory)
- [Enhancing memory retrieval in generative agents through LLM-trained cross attention (Frontiers, 2025)](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2025.1591618/full)
- [AI Agents Need Memory Control Over More Context (arXiv 2601.11653)](https://arxiv.org/html/2601.11653v1)

---

## 10. Emotional Salience Tagging — The Amygdala as a Priority Flag

**What it is**

The amygdala acts as a relevance detector: when an experience carries strong emotional
valence (fear, excitement, frustration, joy), the amygdala floods the hippocampus with
norepinephrine and other modulators that enhance encoding strength. Flashbulb memories
(Brown & Kulik, 1977) are the extreme case: where-were-you-when moments that feel
photographic. A 2023 PNAS meta-analysis confirms there are two distinct neural routes:
one for arousal (amygdala-dependent) and one for valence (hippocampal-prefrontal).
Crucially, the amygdala enhances *confidence and vividness*, not accuracy — emotional
memories are held more strongly but are just as prone to distortion as ordinary ones.

**Why it is surprising**

No AI memory system has a proxy for emotional salience. Notes created during a production
outage at 2am should be encoded with fundamentally different priority than notes created
during calm refactoring on a Tuesday afternoon. The *intensity of the situation* is
information about the importance of the memory, independent of its semantic content.

**How it could apply to Wizard**

- Add a lightweight "intensity signal" to note creation: time of day, session length,
  frequency of context switches in the preceding hour, explicit signals like "production
  incident" or "blocked for N hours." Combine these into a salience score at encoding time.
- High-salience notes should be: (a) stored at higher fidelity, (b) excluded from
  aggressive forgetting-curve decay, (c) always included in session-start context regardless
  of recency, and (d) surfaced first in `what_should_i_work_on`.
- The amygdala caveat — enhanced confidence, not accuracy — has a direct warning for
  Wizard: high-salience memories may be *confidently wrong*. Notes created during a
  production crisis should be marked for reconsolidation review once the crisis is over,
  rather than treated as ground truth.

**Sources**

- [The amygdala mediates the facilitating influence of emotions on memory (PMC, 2023)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10034520/)
- [Two routes to emotional memory: valence and arousal (PNAS)](https://www.pnas.org/doi/10.1073/pnas.0306408101)
- [Flashbulb Memory In Psychology (Simply Psychology)](https://www.simplypsychology.org/flashbulb-memory.html)

---

## 11. Constructive Memory and False Memory Risk — Memory is a Story, Not a Recording

**What it is**

Daniel Schacter's "seven sins of memory" (2001) and Frederic Bartlett's earlier "War of the
Ghosts" experiments show that human memory is *reconstructive*, not reproductive. What you
retrieve is a plausible re-creation that fills gaps with prior knowledge, current beliefs,
and social expectations. Elizabeth Loftus's decades of research on eyewitness testimony
shows that memories can be implanted wholesale through leading questions. MIT Media Lab's
2024 project on AI-implanted false memories found that conversational AI amplified false
memory formation by over 3× in controlled conditions.

**Why it is surprising**

If the brain's memory system is fundamentally reconstructive, then *every AI memory
retrieval that involves synthesis or summarisation is potentially constructive* — the agent
fills gaps with its priors, not with recorded facts. The more synthesis steps between raw
experience and retrieved content, the more the memory has been constructively rewritten.
This is not a bug to eliminate — it is inherent to any memory system that compresses.
The design challenge is knowing *which parts of a memory are original and which are
reconstructed*.

**How it could apply to Wizard**

- Wizard should maintain provenance trails: for every synthesised summary, retain a
  reference back to the raw episodic notes it was derived from. This allows the agent to
  flag when it is presenting synthesised (potentially constructive) content versus
  verbatim-recorded content.
- The `mental_model` field in notes already acknowledges reconstruction ("2-3 sentence
  snapshot of current understanding"). Extend this: tag every mental model with a
  confidence score and a list of the episodic notes it was derived from.
- During a session, if the agent is about to make a claim based on a note that was
  synthesised N steps removed from the original episode, it should explicitly flag the
  reconstruction depth.

**Sources**

- [Constructive memory: past and future (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC3341652/)
- [AI-Implanted False Memories (MIT Media Lab, 2024)](https://www.media.mit.edu/projects/ai-false-memories/overview/)
- [Conversational AI Amplifies False Memories in Witness Interviews (arXiv 2408.04681)](https://arxiv.org/html/2408.04681v1)
- [The AI Memory Gap: Users Misremember What They Created With AI (arXiv 2509.11851)](https://arxiv.org/html/2509.11851)

---

## 12. Memory Engrams and Reactivation — Specific Memory Cells, Not Distributed Haze

**What it is**

Susumu Tonegawa's lab at MIT used optogenetics to identify and reactivate specific sparse
populations of neurons ("engram cells") that encode individual memories. Shining blue light
on the 3-5% of dentate gyrus neurons that were active during fear conditioning is sufficient
to reactivate the full fear memory, even without the original triggering environment.
Remarkably, they created *false memories* by pairing optogenetic reactivation of context-A
engram cells with fear conditioning in context-B — the mice feared context-A, which they
had never been frightened in. Memory is not distributed across all neurons equally; it is
encoded in a specific sparse sub-population.

**Why it is surprising**

This suggests that a well-formed memory is not a search-and-assemble operation across a
database. It is a single structured entity — an engram — that, when activated, rapidly
reconstituces the full experience. The 3-5% sparsity figure is striking: the brain uses
extreme compression ratios. Dense vector stores used in current AI systems approximate this
with embedding similarity, but they treat all dimensions equally. The engram model says most
of the signal lives in a small sparse subset of the representation.

**How it could apply to Wizard**

- Sparse retrieval keys: rather than dense semantic embeddings for every note, experiment
  with sparse high-salience feature keys — the 5-10 most distinctive tokens or concepts
  per memory — as primary index keys, with dense vectors as secondary fallback.
- Engram reactivation maps to Wizard's existing session-start context injection: the goal
  is to find the minimal set of memory records that, when injected into context, reactivate
  the engineer's full prior understanding of the problem. Current context injection is
  additive; engram thinking suggests it should be *curated* — a few high-signal memories
  fully reactivated are worth more than many low-signal memories partially recalled.
- False memory prevention: just as engram reactivation in the wrong context creates false
  memories, injecting task context from one project into a session for a different project
  creates confabulation. Wizard should enforce strict session-level context boundaries.

**Sources**

- [Optogenetic stimulation of a hippocampal engram activates fear memory recall (Nature)](https://www.nature.com/articles/nature11028)
- [Memory engrams: Recalling the past and imagining the future (Science / MIT)](https://dspace.mit.edu/bitstream/handle/1721.1/126261/Submitted%20Version_aaw4325_CombinedPDF_v1.pdf)
- [Inception of a false memory by optogenetic manipulation (MIT)](https://dspace.mit.edu/handle/1721.1/98083)
- [Hippocampal Engrams and Contextual Memory (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12006847/)

---

## 13. The Method of Loci — Spatial Scaffolding Multiplies Memory Capacity

**What it is**

The method of loci (memory palace) dates to ancient Greek and Roman orators who memorised
hours of speech by mentally walking through a familiar building and placing vivid images at
each location. Neuroimaging studies show consistent activation of the hippocampus,
parahippocampus, and retrosplenial cortex — the brain's navigation system — during both
encoding and retrieval. A 2021 *Neuron* paper (Dresler et al.) showed that training naive
subjects in the method of loci for six weeks raised their World Memory Championship scores
from 26 to 62 items and produced measurable changes in functional brain connectivity.

**Why it is surprising**

The brain's spatial navigation system is one of its oldest and most powerful memory
substrates (place cells, grid cells, the Nobel-winning work of the Mosers and O'Keefe). The
method of loci exploits this by piggybacking arbitrary content onto a high-capacity spatial
scaffold. The surprising implication for AI: the agent's "place" in a codebase (which
module, which file, which call stack) is a natural spatial scaffold that could dramatically
improve memory encoding and retrieval.

**How it could apply to Wizard**

- Use the file system and architecture graph as a memory palace. Notes should be
  spatially anchored to code locations (file path, function name, line range) rather than
  tagged only with task IDs and timestamps. Retrieval becomes: "walk through the payment
  service" and pull all memories anchored to nodes in that subgraph.
- This is already partially true (notes have file paths), but the spatial metaphor suggests
  the architecture graph itself — not just individual files — should be a first-class
  retrieval dimension. Moving through `services/ → payment_service.py → process_payment()`
  should trigger progressively more specific memory retrieval.
- For the `what_am_i_missing` tool: generate a coverage map of which code regions have
  dense memory anchoring and which are sparse. Sparse regions are the places the engineer's
  mental model is weakest.

**Sources**

- [Durable memories and efficient neural coding through mnemonic training (PMC, 2021)](https://pmc.ncbi.nlm.nih.gov/articles/PMC7929507/)
- [Method of loci — Wikipedia](https://en.wikipedia.org/wiki/Method_of_loci)
- [How to build a memory palace (Psyche Guides)](https://psyche.co/guides/how-to-build-a-memory-palace-to-store-and-revisit-information)

---

## Cross-Cutting Synthesis

Laying these models side by side reveals three recurring themes that directly challenge
current Wizard architecture:

**1. Memory is active, not archival.** Baddeley's binding, reconsolidation, sleep replay,
predictive coding — every model treats memory as a continuously maintained generative
model, not a passive database. Wizard currently does episodic accumulation + periodic
synthesis. The cognitive models suggest continuous model-maintenance with explicit
surprise-detection as the write trigger.

**2. Forgetting is a feature, not a failure.** Desirable difficulties, sleep consolidation,
retrieval strength decay, the episodic-to-semantic transition — all biological memory
systems deliberately reduce accessibility of non-surprising, well-consolidated content.
Current Wizard stores everything indefinitely at equal retrieval weight. A forgetting
scheduler with salience-weighted decay would make the system more useful, not less.

**3. Context is a primary retrieval key, not a filter.** State-dependent memory, contextual
binding, the memory palace, engram specificity — retrieval in biological systems is
overwhelmingly context-driven. Current RAG-style retrieval treats context as a
post-retrieval ranking signal. The cognitive evidence says context should be the *primary
index dimension*.

---

## 2026 Addenda — Second Research Pass

**Sleep-Consolidated Memory (SCM)** ([arXiv 2604.20943](https://arxiv.org/abs/2604.20943)): Implements literal NREM+REM sleep phases for AI memory consolidation. Achieves 90.9% memory noise reduction with <1ms retrieval latency. The NREM phase prunes contradictions; REM phase replays and reinforces. Applied to Wizard: a nightly consolidation job that runs after all sessions close — not a synthesis hack but a structured two-phase memory transformation.

**Global Workspace Theory implemented** ([arXiv 2604.08206](https://arxiv.org/abs/2604.08206), "Theater of Mind"): Baars' GWT formalised for LLMs — a broadcasting workspace where multiple specialist modules compete to inject context, and only the winning coalition reaches the model. Applied to Wizard: `session_start` becomes a competition between task-memory, temporal-context, and causal-history modules rather than a flat dump of recent notes.

**DPT-Agent: Dual Process Theory** ([arXiv 2502.11882](https://arxiv.org/abs/2502.11882)): Explicit System 1 (fast, pattern-matched, heuristic) + System 2 (slow, deliberate, reasoned) architecture. System 1 handles routine session context injection; System 2 is invoked only when high staleness, contradiction, or novelty is detected. Applied to Wizard: tiered retrieval cost — cheap fast-path for warm sessions, expensive deliberate path only when signals warrant it.

**Cognitive Load Limits in LLMs** ([arXiv 2509.19517](https://arxiv.org/html/2509.19517v2)): Empirical work showing LLMs exhibit working memory capacity limits analogous to Miller's 7±2 and Cowan's 4. Injecting more than ~4 context chunks causes interference, not enrichment. Applied to Wizard: `session_start` context injection should be capped at 4 high-salience items — not "everything recent" — to avoid cognitive load degradation in the agent.
