# Wild Ideas: Multi-Agent Collective Intelligence

_Research memo — May 2026_

**Problem framing:** When multiple wizard agents run in parallel on the same codebase, each agent starts blind. It rediscovers files others already read, re-traces the same call graphs, forms the same (or contradictory) hypotheses. The question is what a genuine collective memory layer looks like — one that goes beyond a shared SQLite database.

---

## Idea 1 — Digital Pheromone Trails (Stigmergy)

**The biological model.** Ants never communicate directly. They deposit chemical trails (pheromones) on paths they've walked; other ants sense trail intensity and amplify it, creating emergent routing. The environment itself carries the coordination signal. Pierre-Paul Grassé called this mechanism _stigmergy_ — indirect coordination through modification of a shared medium.

**Applied to a codebase.** The `.pheromone` file pattern, already implemented in [Pheromind](https://github.com/ChrisRoyse/Pheromind), is the closest practical analogue. Each agent writes structured JSON signals to a shared file whenever it: reads a module, establishes a hypothesis, confirms or rejects a path, or hits a dead end. Other agents read this file before they start exploring and bias their traversal toward high-signal areas (frequently visited, recently updated) and away from already-exhausted paths.

Two distinct signal types map naturally to codebase work:
- **Quantitative stigmergy** (ant pheromone): "This path was explored 4 times and found fruitful — reinforce it." Useful for identifying hot modules.
- **Qualitative stigmergy** (wasp nest): "The shape of what's been built tells you what to build next." Useful for architectural discovery — the partial solution visible in code tells the next agent what's missing.

**The wild extension.** Pheromones _evaporate_. Staleness is built into the model. A finding from 3 days ago should carry less weight than one from 3 minutes ago. Wizard could implement a time-decayed signal store: investigations write weighted breadcrumbs that decay on an exponential schedule. Agents exploring a codebase would see a heatmap of recent attention, not an ever-growing log.

**SwarmSys (Oct 2025) is the most direct LLM implementation of this idea.** It formalises three specialised roles — Explorers, Workers, and Validators — that cycle through exploration, exploitation, and validation. Its pheromone-inspired reinforcement loop is explicit: validated traces strengthen future agent-event compatibility, while idle or invalid matches decay with no reinforcement, mimicking evaporation without a decay timer. Across symbolic reasoning, research synthesis, and scientific programming benchmarks it consistently outperforms baselines on both accuracy and reasoning stability.

A December 2025 arXiv study of emergent collective memory specifically measured stigmergic coordination vs. memory-based coordination in decentralised multi-agent systems. Result: stigmergic traces outperformed memory-based approaches by **36–41% on composite metrics** on realistic large grids, with stigmergic coordination dominating once agent density exceeded roughly 0.20. The key finding — traces written _into the environment_ beat per-agent internal memory — is directly applicable to Wizard's design choice between note logs and structured blackboard signals.

**References:**
- [Pheromind — swarm coordination via .pheromone file](https://github.com/ChrisRoyse/Pheromind)
- [CodeBolt Stigmergy Swarm documentation](https://docs.codebolt.ai/docs/concepts/multi-agent/stigmergy-swarm)
- [Nature: Automatic design of stigmergy-based behaviours for robot swarms](https://www.nature.com/articles/s44172-024-00175-7)
- [SwarmSys: Decentralized Swarm-Inspired Agents for Scalable and Adaptive Reasoning (arXiv 2510.10047)](https://arxiv.org/abs/2510.10047)
- [Emergent Collective Memory in Decentralized Multi-Agent AI Systems (arXiv 2512.10166)](https://arxiv.org/abs/2512.10166)

---

## Idea 2 — The Blackboard Architecture Revival

**The original model.** In classic AI (1970s–80s), the blackboard architecture was the dominant multi-agent coordination pattern. Three components: (1) a shared global data structure — the blackboard — holding the current state of understanding; (2) independent specialist knowledge sources that monitor it and write partial solutions; (3) a control mechanism that selects which knowledge source fires next. No agent needs to know the others exist. They read the board; they write to the board.

**The 2024–25 revival.** Recent work from Google Research and arxiv (Oct 2025) has directly applied this to LLM-based multi-agent systems. In their framework, a central agent posts information requests to a shared blackboard and autonomous subordinate agents — each owning a partition of a data lake — volunteer responses based on their expertise. Crucially, the central coordinator has _no prior knowledge_ of agent capabilities; it discovers them through the blackboard.

Experimental results are striking: the blackboard paradigm outperforms master–slave and RAG baselines by 13–57% in end-to-end task success, with up to 9% F1 gain. The key insight is that the board itself encodes what has been attempted, what succeeded, and what is still open — without any agent needing to maintain that state internally.

**Applied to wizard.** Wizard's SQLite session store is already a proto-blackboard. The wild extension: make it a _structured_ blackboard with explicit slots — hypotheses, confirmed facts, dead ends, open questions — rather than a flat note log. An agent writing a note would classify it into one of these slots. Any subsequent agent loading a session would consume a board state, not a transcript.

**References:**
- [LLM-Based Multi-Agent Blackboard System for Information Discovery in Data Science (arXiv 2510.01285)](https://arxiv.org/abs/2510.01285)
- [Exploring Advanced LLM Multi-Agent Systems Based on Blackboard Architecture (arXiv 2507.01701)](https://arxiv.org/abs/2507.01701)
- [Google Research: Blackboard Multi-Agent Systems for Information Discovery](https://research.google/pubs/blackboard-multi-agent-systems-for-information-discovery-in-data-science/)
- [Building Multi-Agent Systems with MCPs and the Blackboard Pattern (Medium)](https://medium.com/@dp2580/building-intelligent-multi-agent-systems-with-mcps-and-the-blackboard-pattern-to-build-systems-a454705d5672)

---

## Idea 3 — Theory of Mind Between Agents

**The research.** Theory of Mind (ToM) in humans is the capacity to attribute mental states — beliefs, knowledge, intentions — to others and reason about how those states differ from your own. A 2025 CMU PhD dissertation ([Oguntola, CMU-ML-25-118](https://ml.cmu.edu/research/phd-dissertation-pdfs/ioguntol_phd_mld_2025.pdf)) focuses specifically on ToM in multi-agent systems, arguing it is a prerequisite for genuine coordination rather than mere parallel execution.

**The problem it solves.** When two agents are both exploring a codebase, the key question isn't just "what do I know?" — it's "what does the other agent know _that I don't_?" Without ToM, agents broadcast indiscriminately. With it, they could ask: "Agent B has been in `repositories.py` for 20 minutes. It probably knows the DB schema. I don't need to re-read it. I should ask Agent B for its model of the schema and build on that."

**Current state.** The ToMA (Theory of Mind Agent) framework pairs ToM with dialogue lookahead to produce mental state representations that are maximally useful for achieving dialogue goals. CICERO (Meta's Diplomacy AI) demonstrated this at scale: it uses beliefs about other agents' beliefs to negotiate and coordinate without direct interrogation. A workshop dedicated to this is now running at IJCAI 2025.

**The wild extension for wizard.** Each wizard session could maintain a `known_by` annotation alongside findings: "this hypothesis about the auth flow was formed by session X." When a new agent starts, instead of reading all notes, it receives a _belief differential_ — a summary of what it doesn't know yet relative to the collective. The agent explicitly models the collective's knowledge and targets only the gaps. This is the opposite of the current model where each agent reads everything and reconstructs understanding from scratch.

**References:**
- [Theory of Mind in Multi-Agent Systems — CMU PhD Dissertation (2025)](https://ml.cmu.edu/research/phd-dissertation-pdfs/ioguntol_phd_mld_2025.pdf)
- [Theory of Mind in Multi-Agent LLM Collaboration (NLPer.com)](https://nlper.com/2025/07/24/theory-of-mind-multiagent-llm-collaboration/)
- [ToM Workshop at IJCAI 2025](https://tomworkshop.github.io/)
- [Infusing Theory of Mind into Socially Intelligent LLM Agents (arXiv 2509.22887)](https://arxiv.org/html/2509.22887v1)
- [Frontiers: Towards a computational model for higher orders of Theory of Mind in social agents](https://www.frontiersin.org/journals/robotics-and-ai/articles/10.3389/frobt.2024.1468756/full)

---

## Idea 4 — Multi-Agent Debate as Quality Signal

**The research.** The canonical paper (Du et al., ICML 2024) showed that multiple LLM instances proposing answers and critiquing each other's reasoning over several rounds produce outputs that are more factually accurate and solve reasoning questions better than single-agent chain-of-thought. The framing: a "society of minds" where contradictions force resolution. Factual hallucinations drop measurably when contested.

**The asymmetry problem.** More recent work (ICLR 2025 blog post on MAD scaling) reveals a nuance: multi-agent debate fails to consistently outperform single-agent strategies when the debate is homogeneous — same model, same priors, same knowledge. Agents converge to _sycophancy_, reinforcing each other rather than challenging. The CONSENSAGENT paper (ACL 2025) addresses this directly with adaptive prompting to suppress sycophantic convergence.

**The key mechanism: heterogeneity forces quality.** The 2025 paper on adaptive heterogeneous debate found that diverse agents with different specialisations — not just different random seeds — produce the deepest improvement. In codebase context: an agent specialised in security reviewing an agent specialised in performance produces different, complementary attack vectors on the same code.

**Applied to wizard.** When two agents produce conflicting findings (one says "this function is O(n²)", another says "it's batched, O(n)"), the disagreement is currently invisible. A debate layer would surface the conflict, route both claims to a third agent acting as arbiter, and write a resolved finding to the blackboard. The signal is in the disagreement, not in majority vote.

**FREE-MAD (arXiv 2509.11035, Sep 2025) goes further** by eliminating consensus entirely. Each agent provides not just an answer but a full reasoning trace; the next round's agents analyse _the reasoning_, not just the conclusion. An agent whose reasoning is sound assigns low probability to a flawed majority answer regardless of how many agree with it — anti-conformity is explicit. The score-based decision mechanism evaluates the entire debate trajectory, not the final round. Net result: equivalent performance in a single debate round vs. multiple rounds, reducing token costs substantially.

**References:**
- [Improving Factuality and Reasoning in LLMs through Multiagent Debate (ICML 2024)](https://composable-models.github.io/llm_debate/)
- [Multi-LLM-Agents Debate — Performance, Efficiency, and Scaling Challenges (ICLR Blogposts 2025)](https://d2jud02ci9yv69.cloudfront.net/2025-04-28-mad-159/blog/mad/)
- [CONSENSAGENT: Towards Efficient and Effective Consensus via Sycophancy Mitigation (ACL 2025)](https://aclanthology.org/2025.findings-acl.1141/)
- [FREE-MAD: Consensus-Free Multi-Agent Debate (arXiv 2509.11035)](https://arxiv.org/abs/2509.11035)
- [Adaptive heterogeneous multi-agent debate — Springer 2025](https://link.springer.com/article/10.1007/s44443-025-00353-3)
- [Multi-Agent Debate Strategies for Requirements Engineering (arXiv 2507.05981)](https://arxiv.org/html/2507.05981v1)

---

## Idea 5 — Federated Knowledge: Share Gradients, Not Sessions

**The model.** Federated learning (Google Brain, 2017) was designed for a privacy constraint: you can't centralise the training data, but you can centralise the model updates. Each participant trains locally, sends only weight deltas to a coordinator, and receives an improved global model. Critically, no raw data ever leaves the device. The pattern: _share what you learned, not what you saw_.

**Applied to multi-agent memory.** The direct analogy: each wizard agent runs a session, accumulates findings, and at session end, instead of writing raw notes to shared memory, it writes _distilled patterns_ — compact, abstracted representations of what it learned. The raw session transcript stays local (or is discarded). Downstream agents receive the synthesised learning.

This is the inverse of the current wizard model, where `transcript_raw` accumulates and synthesis is a post-hoc compression. In a federated model, synthesis _is_ the write path. Agents would contribute to a shared "gradient" of codebase understanding that improves with each session without exposing the raw context that might include sensitive user data or noisy dead ends.

**Federated Reinforcement Learning extension.** A more exotic variant: agents that use RL to adapt their exploration strategies would share policy updates rather than trajectories. An agent that learned "when you see a file with 400+ lines of SQL, start from the query builder not the model class" would contribute that learned heuristic to the collective without exposing the specific files it encountered.

**References:**
- [Federated Learning: A Survey on Privacy-Preserving Collaborative Intelligence (arXiv 2504.17703)](https://arxiv.org/html/2504.17703v3)
- [TechDispatch #1/2025 — Federated Learning (European Data Protection Supervisor)](https://www.edps.europa.eu/data-protection/our-work/publications/techdispatch/2025-06-10-techdispatch-12025-federated-learning_en)
- [Federated Learning in 2025: What You Need to Know (DEV Community)](https://dev.to/lofcz/federated-learning-in-2025-what-you-need-to-know-3k2j)

---

## Idea 6 — MAGMA-Style Multi-Graph Memory

**The research.** MAGMA (arXiv 2601.03236, Jan 2026) proposes that agent memory should not be a flat vector store. Every memory item should be simultaneously encoded in four orthogonal graphs: semantic (what it's about), temporal (when it happened), causal (what caused what), and entity (which code objects are involved). Retrieval is then policy-guided traversal across these graphs rather than nearest-neighbour lookup in embedding space.

The results are striking: 18.6–45.5% improvement over baselines on long-horizon memory benchmarks, with 95% reduction in token consumption vs. full-context retrieval and 40% faster query latency than the next best approach.

**The core insight.** Semantic similarity alone is insufficient. "The auth module is slow" and "the auth module has a security issue" are semantically similar and would be retrieved together — but they're causally unrelated findings that should be kept separate. Multi-graph encoding preserves the orthogonal structure of knowledge.

**Applied to wizard's collective memory.** Each wizard investigation note has a natural multi-graph encoding: it's about certain concepts (semantic), happened at a time (temporal), was triggered by a hypothesis (causal), and touched specific code entities (entity graph). When a new agent asks "what's known about the database write path?", the traversal follows entity graph edges to relevant modules, then causal edges backward to root causes, then temporal edges to find the most recent updates. This retrieval is far more precise than embedding similarity against a flat note store.

**References:**
- [MAGMA: A Multi-Graph based Agentic Memory Architecture for AI Agents (arXiv 2601.03236)](https://arxiv.org/abs/2601.03236)
- [AriGraph: Learning Knowledge Graph World Models with Episodic Memory (IJCAI 2025)](https://www.ijcai.org/proceedings/2025/0002.pdf)
- [Graph-Based Agent Memory: A Complete Guide (Medium)](https://shibuiyusuke.medium.com/graph-based-agent-memory-a-complete-guide-to-structure-retrieval-and-evolution-6f91637ad078)
- [Memory in LLM-based Multi-agent Systems: Mechanisms, Challenges, and Collective (TechRxiv)](https://www.techrxiv.org/users/1007269/articles/1367390)
- [A-Mem: Agentic Memory for LLM Agents (arXiv 2502.12110)](https://arxiv.org/pdf/2502.12110)

---

## Idea 7 — Emergent Communication and Agent-Invented Protocols

**The research.** A surprising finding from 2024 (arXiv 2510.05174): when multi-agent LLM systems are given a shared environment and a shared goal but _not_ a shared communication protocol, they spontaneously develop one. Identity-linked differentiation emerges — agents begin to speak to each other in ways that exploit their respective specialisations, without being instructed to do so. The term used is "goal-directed complementarity."

This connects to a broader result from the same year: a multi-agent discussion approach outperformed single-agent chain-of-thought prompting specifically because a collection of mediocre reasoners, when allowed to interact freely, produced superior outcomes. The interaction _itself_ generates capability that no individual agent had.

**The deeper idea: qualitative phase transitions.** The preprint "Multi-Agent LLM Systems: From Emergent Collaboration to Structured Collective Intelligence" (Preprints.org 2511.1370) proposes that multi-agent systems can be steered through distinct regimes — competition, collaboration, coordination — and that different task families respond to different regime designs. The wild implication: for a codebase exploration task, a _competition_ regime (agents racing to find a bug first) may outperform a _collaboration_ regime (agents dividing the codebase) because competitive pressure prevents premature convergence on a wrong hypothesis.

**Applied to wizard.** Rather than assigning tasks to agents, give all agents the same goal and let them develop specialisation organically. An agent that repeatedly finds security issues will start self-labelling as the "security lens." The specialisation is not pre-assigned — it emerges from interaction with the shared environment. The blackboard captures who found what, and the pattern of contributions shapes the implicit roles.

**References:**
- [Emergent Coordination in Multi-Agent Language Models (arXiv 2510.05174)](https://arxiv.org/abs/2510.05174)
- [Multi-Agent LLM Systems: From Emergent Collaboration to Structured Collective Intelligence (Preprints.org 202511.1370)](https://www.preprints.org/manuscript/202511.1370)
- [Emergent Communication Protocols in Multi-Agent Systems (ResearchGate)](https://www.researchgate.net/publication/388103504_Emergent_Communication_Protocols_in_Multi-Agent_Systems_How_Do_AI_Agents_Develop_Their_Languages)
- [Multi-Agent Cooperative Decision-Making: Survey (arXiv 2503.13415)](https://arxiv.org/html/2503.13415v1)

---

## Idea 8 — Belief Merging and Epistemic Conflict Resolution

**The problem.** When two agents investigate the same codebase and disagree — one concludes "the N+1 is in the sync service", another concludes "the N+1 is in the task loader" — current systems have no principled way to resolve the conflict. The naive answer is last-write-wins. The less naive answer is majority vote. Both are wrong.

**The research.** Formal belief merging (a subfield of epistemic logic) has studied this for decades but the 2025 work brings it to LLMs. Key insight from ACL 2025: _implicit consensus_ consistently outperforms _explicit consensus_ in multi-agent systems. Agents that merge beliefs through continued reasoning about shared evidence (implicit) outperform agents that vote or take turns asserting (explicit). The sycophancy trap — agents deferring to each other rather than evidence — is the key failure mode explicit consensus amplifies.

The CONSENSAGENT framework addresses this by dynamically refining debate prompts based on observed agent interactions, specifically to detect and suppress sycophantic convergence. The signal for sycophancy is rapid unanimous agreement after minimal challenge — which is different from well-reasoned convergence.

A related result from Bayesian multi-agent reasoning (arXiv 2506.08292): Bayesian belief updating, where agents maintain probability distributions over hypotheses and update them based on evidence from other agents, outperforms both voting and sequential debate. Confidence, not just conclusion, should propagate.

**Applied to wizard.** When wizard detects that two sessions have written conflicting findings about the same code entity, it should flag the conflict rather than silently overwriting. The resolution path: a third agent reads both findings and the underlying code, and writes a resolved belief with an explicit confidence score. The conflict itself — the fact that two competent agents reached different conclusions — is a signal that the code is genuinely ambiguous, which is itself a high-value finding.

**References:**
- [Unraveling the Consensus-Diversity Tradeoff in Adaptive Multi-Agent Systems (EMNLP 2025)](https://aclanthology.org/2025.emnlp-main.772.pdf)
- [CONSENSAGENT: Towards Efficient and Effective Consensus via Sycophancy Mitigation (ACL 2025)](https://aclanthology.org/2025.findings-acl.1141/)
- [Belief-Driven Multi-Agent LLM Reasoning via Bayesian approaches (arXiv 2506.08292)](https://arxiv.org/pdf/2506.08292)
- [Efficient Multi-Agent Epistemic Planning: Teaching Planners about Nested Belief (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S0004370221001569)
- [Argumentation as Distributed Belief Revision in Multi-Agent Systems (Springer)](https://link.springer.com/chapter/10.1007/3-540-45329-6_22)

---

## Idea 9 — Transactive Memory: "Who Knows What" as a First-Class Primitive

**The concept.** Transactive Memory Systems (TMS) are a well-studied phenomenon in organisational psychology: high-performing teams don't just share knowledge, they maintain a shared _meta-knowledge_ about where knowledge lives. Each member knows what others know and routes queries accordingly. A surgeon doesn't memorise anaesthesia dosages — she knows the anaesthesiologist knows. The team's collective recall capacity exceeds any individual's precisely because they've offloaded expertise tracking to a shared map.

**Applied to LLM agents.** Google Research published a paper explicitly framing AI agents within TMS theory: "Teamwork Makes the Dream Work: Framing AI Agents Within Transactive Memory Theory." The core observation is that current LLM multi-agent systems replicate the _worst_ human team failure mode — everyone re-learns everything because no one tracks who knows what. The paper identifies three TMS properties that AI teams lack: _specialisation_ (agents have differentiated knowledge), _credibility_ (agents trust peers with relevant expertise), and _coordination_ (agents route queries to the right peer rather than rediscovering independently).

A 2025 survey of memory mechanisms in LLM-MAS formalised this: just as human teams develop TMS, LLM-based agents require similar meta-memory capabilities to efficiently allocate cognitive resources and avoid redundant processing. The mechanism they propose is explicit transactive memory — a team-level data structure that tracks agent-to-knowledge mappings, distinct from any agent's local memory.

**Collaborative Memory with access control (May 2025, arXiv 2505.18279).** This paper attacks the multi-user variant of the same problem. The framework encodes time-evolving permissions as bipartite graphs linking users, agents, and memory resources. Each edge carries an access predicate. When a new agent joins a session it receives precisely the knowledge it has access to — no more. The two-tier design (private memory per user + shared memory for permitted cross-user access) is directly analogous to what a team of engineers using Wizard would need: personal notes stay private; architectural decisions are shared.

**The wild extension for wizard.** Wizard currently has no concept of agent specialisation. After enough sessions, the note store implicitly encodes who found what — but no agent knows to ask. A TMS layer would maintain a live map: `{ "auth_service": ["session_4a", "session_7c"], "db_schema": ["session_2b"] }`. When a new agent starts, it queries this map first — "who has covered the auth service?" — and either retrieves that agent's synthesis directly or defers to it rather than re-reading the same files. The coordination is indirect and persistent: it lives in the shared environment, not in any agent's context window.

**References:**
- [Teamwork Makes the Dream Work: Framing AI Agents Within Transactive Memory Theory (Google Research, 2025)](https://research.google/pubs/teamwork-makes-the-dream-work-framing-ai-agents-within-transactive-memory-theory/)
- [Collaborative Memory: Multi-User Memory Sharing in LLM Agents with Dynamic Access Control (arXiv 2505.18279)](https://arxiv.org/abs/2505.18279)
- [Memory in LLM-based Multi-agent Systems: Mechanisms, Challenges, and Collective Intelligence (TechRxiv)](https://www.techrxiv.org/doi/full/10.36227/techrxiv.176539617.79044553/v1)
- [Scaling Teams or Scaling Time? Memory Enabled Lifelong Learning in LLM Multi-Agent Systems (arXiv 2604.03295)](https://arxiv.org/abs/2604.03295)
- [The group mind of hybrid teams with humans and intelligent agents (Sage Journals, 2025)](https://journals.sagepub.com/doi/10.1177/02683962241296883)

---

## Synthesis: What Would a Genuine Collective Layer Look Like?

Drawing across these ideas, a collective memory layer for wizard agents would have at least six properties absent from a simple shared database:

1. **Spatiotemporal decay** (from stigmergy): findings carry timestamps and their influence diminishes over time. Old hypotheses are deprioritised, not just archived. The empirical backing from arXiv 2512.10166 is strong: trace-based coordination outperforms in-agent memory by 36–41%, and the evaporation mechanism in SwarmSys (arXiv 2510.10047) demonstrates this is implementable in LLM agent frameworks today.

2. **Typed slots** (from blackboard): the board isn't a flat log. It has explicit slots for hypotheses, confirmed facts, dead ends, open questions, and conflicts. Agents write to the right slot; readers know what they're consuming. The arXiv 2510.01285 blackboard result (13–57% improvement over RAG and master–slave baselines) suggests the structure itself — not just the content — is doing real work.

3. **Belief differentials** (from Theory of Mind): when an agent starts a session, it receives not the full collective memory but the delta — what it doesn't know yet relative to what the collective knows.

4. **Conflict surfacing** (from belief merging): contradictions are first-class citizens. Two agents reaching opposite conclusions about the same code is a signal, not noise. The conflict persists until explicitly resolved by a designated arbiter. FREE-MAD (arXiv 2509.11035) demonstrates that preserving and evaluating reasoning traces — not just conclusions — is the mechanism that prevents sycophantic collapse.

5. **Emergent role capture** (from emergent communication): the system tracks what each agent-session contributed (security findings, performance findings, architectural findings) and builds an implicit specialisation map. New agents can be seeded with "you are entering a context where agent B has covered security — focus elsewhere."

6. **Transactive meta-memory** (from TMS): a first-class map of `entity → [sessions that covered it]` so that new agents query the map before re-reading files. The Collaborative Memory access control model (arXiv 2505.18279) shows this is buildable with bipartite permission graphs — a natural fit for Wizard's existing session model.

The closest existing system to this combination is Pheromind's `.pheromone` file (decay + traces) combined with MAGMA's multi-graph retrieval (structured, typed memory) and a TMS index (meta-knowledge routing) — none of which wizard currently uses, but each of which is adoptable incrementally as its own well-scoped feature.
