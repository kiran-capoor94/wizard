# Wild Idea #09: Imagination, Simulation, and Predictive Memory

**Filed:** 2026-05-02
**Status:** Speculative — research synthesis only

---

## The Core Question

Wizard is currently a backward-looking system. It records what happened, synthesises sessions, and surfaces relevant history on request. The radical alternative: memory as a *generative forward model* — a system that uses accumulated past decisions to simulate likely futures, predict failures before they occur, and proactively surface "you are about to repeat a pattern that collapsed 3 months ago."

This document surveys the research landscape for ideas that could inform such a direction.

---

## 1. World Models: Memory as a Simulator of the Future

### The LeCun JEPA Architecture

Yann LeCun's "A Path Towards Autonomous Machine Intelligence" (2022, OpenReview) argues that genuine intelligence requires a **world model** — an internal module that predicts plausible future states given a current state and a contemplated action. This is qualitatively different from a retrieval system. The world model does not look up what happened; it *runs forward* to estimate what *will* happen.

The practical realisation is the **Joint Embedding Predictive Architecture (JEPA)**: instead of reconstructing raw inputs (pixels, tokens), JEPA predicts abstract *representations* of future states in a latent embedding space. This means the model learns to ignore irrelevant noise and compress experience into the semantically meaningful structure that governs future outcomes.

The 2024 **V-JEPA** extension applies this to video — learning world dynamics from 2M+ unlabelled clips without contrastive pairs or text labels. **LLM-JEPA** (arXiv:2509.14252) brings the same objective to language models, outperforming standard LLM training objectives by a significant margin.

**Applied to Wizard:** Each session and decision in the memory store is training data for a latent model of *how this person's projects tend to evolve*. Instead of only asking "what have I done?", the system could ask "given my current trajectory, what state is this project likely to be in in 6 weeks?" — not via retrieval but via forward simulation in the embedding space of accumulated experience.

**References:**
- [A Path Towards Autonomous Machine Intelligence — LeCun (OpenReview)](https://openreview.net/pdf?id=BZ5a1r-kVsf)
- [V-JEPA: The next step toward advanced machine intelligence — Meta AI](https://ai.meta.com/blog/v-jepa-yann-lecun-ai-model-video-joint-embedding-predictive-architecture/)
- [LLM-JEPA: Large Language Models Meet Joint Embedding Predictive Architectures (arXiv:2509.14252)](https://arxiv.org/abs/2509.14252)
- [I-JEPA: Self-Supervised Learning from Images with a JEPA (arXiv:2301.08243)](https://arxiv.org/abs/2301.08243)

---

## 2. Imagination-Based Reinforcement Learning: Planning in Dream Space

### DreamerV3

Danijar Hafner's **DreamerV3** (published in *Nature*, 2025; arXiv:2301.04104) learns a compact world model from experience, then plans *entirely inside that model* — never touching the real environment during planning. The agent imagines thousands of futures in latent space, evaluates them with a learned value function, and only acts on the conclusion. This is "thinking in dreams."

The critical insight for knowledge-work applications: the bottleneck in complex planning is not computation but *getting enough real-world feedback*. DreamerV3 addresses this by making the *memory itself* a simulator. The historical record is not queried — it is *run*.

DreamerV3 works out of the box on 150+ diverse tasks with a single fixed hyperparameter configuration, including Minecraft diamond collection from raw pixels — a long-horizon planning problem with sparse rewards, structurally similar to multi-month engineering projects.

**UniZero** (arXiv:2406.10667) extends this with a transformer-based latent world model that separates latent state from implicit history, enabling joint optimisation for long-horizon planning — directly relevant to the multi-month time horizons of a personal productivity system.

**Applied to Wizard:** A Dreamer-style component over Wizard's session history would not retrieve past sessions — it would *simulate forward*. "Given the last 30 sessions, what is the most likely next three weeks?" Running that simulation cheaply, in latent space, would surface predictions like: "You have entered a phase that historically precedes a dropped project."

**References:**
- [Mastering Diverse Control Tasks through World Models — DreamerV3 (Nature)](https://www.nature.com/articles/s41586-025-08744-2)
- [DreamerV3 project page — danijar.com](https://danijar.com/project/dreamerv3/)
- [UniZero: Generalized and Efficient Planning with Scalable Latent World Models (arXiv:2406.10667)](https://arxiv.org/html/2406.10667v1)
- [Evaluating World Models with LLM for Decision Making (arXiv:2411.08794)](https://arxiv.org/abs/2411.08794)

---

## 3. Active Inference: Memory as Minimising Surprise About the Future

### Friston's Free Energy Principle

Karl Friston's **Free Energy Principle** and its corollary **Active Inference** (PMC articles, Friston et al.) propose that intelligent agents do not passively record the past — they maintain a *generative model* of the world and act to minimise the discrepancy between predicted future states and preferred future states. Planning *is* simulation: the agent evaluates policies by imagining their consequences and choosing the policy that minimises expected surprise (free energy).

The forward-looking nature is essential. The agent does not store events; it stores a *probabilistic model of what comes next*. Memory, in this framework, is the parameterisation of that generative model — continuously updated by prediction errors. A 2024 paper (arXiv:2402.14460) re-examines the Expected Free Energy formulation, strengthening the case for AI implementations.

This framework has a direct translation: **every time Wizard records a decision, it is a training signal that updates a generative model of the user's future**. The system is not writing to an archive — it is sharpening a forward model.

**Applied to Wizard:** An active inference agent embedded in Wizard would not surface memories when asked. It would continuously generate predictions ("your next session will likely involve X") and flag when observed behaviour deviates from the model's prediction — a strong signal that something has changed and warrants attention.

**References:**
- [Active Inference and the Free Energy Principle — Tasshin.com overview](https://tasshin.com/blog/active-inference-and-the-free-energy-principle/)
- [Reframing the Expected Free Energy (arXiv:2402.14460)](https://arxiv.org/pdf/2402.14460)
- [From Neuroscience to AI: Karl Friston's Free Energy Principle (ResearchGate)](https://www.researchgate.net/publication/397380587_From_Neuroscience_to_Artificial_Intelligence_Karl_Friston_s_Free_Energy_Principle_and_the_Rise_of_Active_Inference)
- [Generalised free energy and active inference — PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC6848054/)

---

## 4. Episodic Future Thinking and Mental Time Travel

### Cognitive Science Foundation

The neuroscience of memory is instructive: the hippocampus does not store and replay the past — it *recombines* episodic fragments to *simulate novel futures*. This is called **Episodic Future Thinking (EFT)** or **mental time travel**. Suddenly, Corballis, and Mahr & Schacter (2024) distinguish the temporal component of memory from the recombination process: the same neural machinery that remembers a past event *constructs* a plausible future event.

A January 2024 UCL/ScienceDaily study used generative AI models to explain this dual function — showing that variational autoencoders trained on episodic data develop the same gist-plus-detail structure that allows forward simulation from fragments.

The **constructive episodic simulation hypothesis** (Addis, Schacter) is the key idea: memory stores are not recordings; they are parts bins for constructing simulations. The fact that memories are *reconstructive* — and sometimes wrong — is not a bug. It is the same mechanism that allows them to be *generative*.

**Applied to Wizard:** The past sessions in Wizard are not recordings of ground truth — they are fragments that can be recombined into plausible future scenarios. A system implementing EFT would not answer "what happened on project X?" but "here is a plausible scenario for the next phase of project X, assembled from fragments of how similar projects developed."

**References:**
- [Episodic Future Thinking — MIT Open Encyclopedia of Cognitive Science](https://oecs.mit.edu/pub/d16msun2)
- [Generative AI helps explain human memory and imagination — UCL News (Jan 2024)](https://www.ucl.ac.uk/news/2024/jan/generative-ai-helps-explain-human-memory-and-imagination)
- [A generative model of memory construction and consolidation — Nature Human Behaviour](https://www.nature.com/articles/s41562-023-01799-z)
- [Episodic future thinking and episodic counterfactual thinking — ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1074742713002633)

---

## 5. Counterfactual Simulation: Learning from Roads Not Taken

### Counterfactual World Simulation Models

A 2025 paper in *AI and Ethics* (Kirfel et al., Stanford CICL) describes **counterfactual world simulation models (CWSMs)**: AI systems that build a high-fidelity reconstruction of a past situation and then answer causal questions by simulating what would have happened under different conditions. The example in the paper is accident reconstruction from CCTV, but the underlying mechanism — reconstruct, vary one variable, re-simulate — is domain-general.

Causal RL research (CRL Lab) has formalised this: causal inference allows agents to reason about counterfactual outcomes even when *no data about the imagined reality is available*, using structural invariances extracted from observed trajectories.

A 2025 paper (arXiv:2505.12701) introduces counterfactual explanations specifically for continuous-action RL: "what sequence of alternative actions would have led to a better outcome while minimally deviating from what actually happened?" This is pre-mortem analysis applied retroactively, but the same engine works prospectively.

**Applied to Wizard:** When a task is marked failed or dropped, Wizard could run a counterfactual simulation: "here are three alternative decision sequences from session 4 that, based on past patterns, would likely have avoided this outcome." Accumulated across many such simulations, the system learns which decision variables have the largest counterfactual impact on outcomes — and surfaces them as warnings in real-time.

**References:**
- [When AI meets counterfactuals: ethical implications of CWSMs — AI and Ethics (Springer, 2025)](https://link.springer.com/article/10.1007/s43681-025-00718-4)
- [Causal Reinforcement Learning — CRL Lab](https://crl.causalai.net/)
- [Counterfactual Explanations for Continuous Action RL (arXiv:2505.12701)](https://arxiv.org/abs/2505.12701)
- [Explaining RL Agents through Counterfactual Action Outcomes — AAAI 2024](https://ojs.aaai.org/index.php/AAAI/article/view/28863)

---

## 6. Prospective Memory: Remembering to Do Future Things

### Cognitive Architecture Gap

In cognitive psychology, **prospective memory** is the ability to remember to do something at a future point — a meeting you intend to call, a follow-up you intended to send. This is structurally distinct from retrospective memory (recall of the past). It is inherently predictive: the system must hold an intention, model the conditions under which that intention becomes relevant, and fire at the right moment.

A 2025 paper ("In Prospect and Retrospect: Reflective Memory Management for Long-term Personalized Dialogue Agents") explicitly addresses this gap in LLM agent architectures. The current state of the art, surveyed in the 107-page "Memory in the Age of AI Agents" (arXiv:2512.13564, December 2025), identifies prospective memory as underdeveloped — most agent memory systems are purely retrospective (what was said), not prospective (what was intended but not yet done).

**Applied to Wizard:** Most of what Wizard records are retrospective artefacts: decisions made, tasks completed, notes saved. But a significant fraction of every session contains *prospective commitments* — "I need to check X", "remind me to revisit Y when Z happens". Today these are buried. A prospective memory subsystem would extract them at write time, maintain them as forward-looking obligations with trigger conditions, and surface them when those conditions are met — including conditions the user never made explicit but that Wizard can infer from context.

**References:**
- [Memory in the Age of AI Agents: A Survey (arXiv:2512.13564)](https://arxiv.org/abs/2512.13564)
- [ICLR 2026 Workshop Proposal: MemAgents — Memory for LLM-Based Agentic Systems (OpenReview)](https://openreview.net/pdf?id=U51WxL382H)
- [Position: Episodic Memory is the Missing Piece for Long-Term LLM Agents (arXiv:2502.06975)](https://arxiv.org/pdf/2502.06975)
- [Long-Term Memory: Unlocking Smarter, Scalable AI Agents — AI Practitioner](https://aipractitioner.substack.com/p/long-term-memory-unlocking-smarter-38d)

---

## 7. Generative Agents and the Reflection Loop

### Stanford Smallville

Park et al. (2023, arXiv:2304.03442) demonstrated **generative agents** — LLM-backed simulated personas that maintain a running stream-of-consciousness memory, periodically *reflect* on that stream to generate higher-order abstractions, and then use those abstractions to plan future behaviour. The architecture has three layers: memory stream (raw events), reflection (periodic synthesis of patterns), and planning (forward projection of goals).

The critical mechanism is the **reflection trigger**: agents reflect when accumulated memory *importance scores* exceed a threshold. This is a noise-resistant signal that something worth updating beliefs about has occurred. The resulting reflection is not a summary — it is a *hypothesis* about the agent's world.

Follow-up work ("Affordable Generative Agents", arXiv:2402.02053) reduces the computational cost, making continuous background reflection tractable.

**Applied to Wizard:** Wizard's synthesis layer already implements something like the memory stream. What it lacks is the *reflection → planning* loop. After synthesis, the system could ask: "given the pattern revealed by this synthesis, what is most likely to happen in the next 2 weeks?" and store that as a standing hypothesis. Subsequent sessions confirm or refute the hypothesis, updating the agent's prior. Over time, Wizard builds calibrated predictions about the user's future rather than just a record of their past.

**References:**
- [Generative Agents: Interactive Simulacra of Human Behavior (arXiv:2304.03442)](https://arxiv.org/abs/2304.03442)
- [Affordable Generative Agents (arXiv:2402.02053)](https://arxiv.org/pdf/2402.02053)
- [Generative Agents ACM DL full HTML](https://dl.acm.org/doi/fullHtml/10.1145/3586183.3606763)

---

## 8. Temporal Knowledge Graphs: Memory with a Validity Window

### Zep / Graphiti

The **Zep architecture** (arXiv:2501.13956, January 2025) introduces a fundamentally different memory representation: a **temporal knowledge graph** where every stored fact has a *validity window* — when it became true and when (if ever) it was superseded. This is not an archive; it is a time-indexed world-state model.

The key design choice: Graphiti does not recompute the full graph on each update. It integrates new information incrementally, maintains historical snapshots, and supports queries like "what did the agent believe to be true about X on date Y?" This enables **temporal reasoning** — not just retrieval, but reasoning about how beliefs evolved over time.

Zep achieves 18.5% accuracy improvement on LongMemEval (complex temporal reasoning) while reducing response latency by 90% compared to baseline retrieval systems.

**Applied to Wizard:** A temporal knowledge graph of the user's beliefs, project states, and commitments would allow Wizard to detect when a current belief contradicts a past belief — a signal of context drift. More powerfully, it enables queries like: "what was the state of this project in February, what did I predict would happen, and how does the actual outcome compare?" This closes the prediction-reality feedback loop that makes the forward model improve over time.

**References:**
- [Zep: A Temporal Knowledge Graph Architecture for Agent Memory (arXiv:2501.13956)](https://arxiv.org/abs/2501.13956)
- [Zep Graphiti GitHub](https://github.com/getzep/graphiti)
- [Zep blog post](https://blog.getzep.com/zep-a-temporal-knowledge-graph-architecture-for-agent-memory/)

---

## 9. Speculative Execution Applied to Agent Actions

### Parallel Future Paths

A 2025 paper (arXiv:2510.04371, "Speculative Actions: A Lossless Framework for Faster Agentic Systems") applies the CPU speculative execution metaphor directly to AI agents: predict the most likely next N actions using a fast model, begin executing them in parallel, and roll back any that turn out to be wrong. In testing, next-action prediction accuracy reaches 55%, yielding significant end-to-end latency reduction.

The mechanism is lossless — no speculative result is committed until validated. The cost of a misprediction is a rollback, not an error. This makes the approach applicable to any environment where actions have observable outcomes and rollbacks are cheap.

**Applied to Wizard:** The same principle applies to *reasoning ahead* rather than acting ahead. Before the user's next session begins, Wizard could speculatively synthesise what it expects the session to surface, pre-load relevant context, and prepare a draft hypothesis. If the session confirms the speculation, zero retrieval cost is paid. If it does not, the draft is discarded and a fresh synthesis runs. This is memory as pre-fetch cache — the system guesses what you need before you ask.

**References:**
- [Speculative Actions: A Lossless Framework for Faster Agentic Systems (arXiv:2510.04371)](https://arxiv.org/abs/2510.04371)

---

## 10. Hippocampal Replay as Offline Reinforcement Learning

### The Neuroscience of Offline Planning

A 2024 paper in *Frontiers in Computational Neuroscience* ("Memory consolidation from a reinforcement learning perspective") proposes that hippocampal sleep replay is not just memory consolidation — it is **offline reinforcement learning**. During replay, the hippocampus re-runs past experiences, evaluating which decisions led to good outcomes, and reinforces valuable future strategies through simulated experience. Memory *is* planning.

The implication: a system that replays past decisions during idle time — not to archive them, but to simulate variants and evaluate outcomes — would develop an increasingly accurate model of which decision types lead to success for this specific user, in this specific context.

A predictive coding model of hippocampo-neocortical interactions (OpenReview, 2024) formalises the mechanism: the hippocampus generates predictions, the neocortex provides context, and prediction errors drive both memory update and generalisation to novel situations.

**Applied to Wizard:** Between sessions, Wizard could run an offline replay pass over the last N months of decisions — not to summarise them, but to evaluate them counterfactually. Which task-start decisions led to completion? Which decision types correlate with abandonment? The result is not a report but a calibrated prior that shapes how the system weights future recommendations.

**References:**
- [Memory consolidation from a reinforcement learning perspective — Frontiers in Computational Neuroscience (2024)](https://www.frontiersin.org/journals/computational-neuroscience/articles/10.3389/fncom.2024.1538741/full)
- [A predictive coding model of hippocampo-neocortical interactions — OpenReview](https://openreview.net/forum?id=9BrQAIH1dS)
- [Prediction errors disrupt hippocampal representations and update episodic memories — PNAS](https://www.pnas.org/doi/10.1073/pnas.2117625118)

---

## Synthesis: What Would a Forward-Looking Wizard Look Like?

The research across these ten threads converges on a small number of structural changes that would transform Wizard from an archive into a predictive engine:

| Layer | Current | Forward-looking |
|---|---|---|
| Memory representation | Event log + synthesis | Temporal knowledge graph with validity windows (Zep/Graphiti) |
| Synthesis output | Summary of what happened | Hypothesis about what will happen (Generative Agents reflection loop) |
| Retrieval | Query → recall | Prediction → confirm/refute feedback loop |
| Failure detection | None | Counterfactual simulation on task completion/abandonment |
| Prospective obligations | Buried in session text | Extracted at write-time, monitored for trigger conditions |
| Idle processing | None | Offline RL replay to update decision priors |

The most tractable first step is the smallest: after every synthesis, generate a *standing prediction* — a 2-sentence hypothesis about the most likely development in the next two weeks. Store it. At the start of the following session, evaluate it. This requires no new infrastructure. It just requires writing a prediction at synthesis time and checking it at session-start time. Over 30 sessions, those 30 prediction/outcome pairs are the raw material for everything else described here.
