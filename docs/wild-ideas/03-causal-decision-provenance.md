# Wild Ideas: Causal Decision Provenance

*Research sweep — May 2026*

The core unsolved problem for Wizard: how do you capture *why* a decision was made, not just *what* was decided? How do you store the counterfactual — "we ruled out approach X because Y" — in a way that's queryable months later?

This document collects the most useful and surprising research across causal reasoning, counterfactual memory, decision provenance, and AI explainability, with direct implications for rethinking how Wizard stores engineer reasoning.

---

## 1. Chain-of-Thought Is Not Explainability (Oxford, 2025)

**The finding:** CoT chains are not faithful records of how a model actually decided — they are post-hoc rationalizations. Oxford's whitebox AI group published a paper with this exact title in 2025. Intervention studies show that final answers frequently remain unchanged even when intermediate CoT steps are falsified or omitted — the "illusion of transparency." Even reasoning-trained models like DeepSeek-R1 acknowledged prompt hints in only 59% of cases and failed to surface problematic influences 41% of the time.

**Why it's wild:** The industry has collectively assumed that "chain of thought" = "the decision process." This research proves that assumption is false by construction: the model generates the explanation *after* the computation, not alongside it. The narrative is a retelling, not a recording.

**Implication for Wizard:** If you store Claude's reasoning trace as the decision rationale, you are storing a plausible-sounding story, not the actual causal chain. This is the foundational problem: the surface explanation and the real cause diverge. Any decision memory system has to acknowledge this gap and find other anchoring mechanisms — structured fields, action traces, and external constraints rather than free-text rationale.

**Sources:**
- [Chain-of-Thought Is Not Explainability (Oxford WhiteBox, 2025)](https://aigi.ox.ac.uk/wp-content/uploads/2025/07/Cot_Is_Not_Explainability.pdf)
- [Lie to Me: How Faithful Is Chain-of-Thought Reasoning in Open-Weight Reasoning Models?](https://arxiv.org/html/2603.22582v1)
- [Measuring Chain of Thought Faithfulness by Unlearning Reasoning Steps](https://arxiv.org/html/2502.14829v3)

---

## 2. Causal Abstraction as a Theoretical Foundation for Interpretability (Geiger et al., 2023–2025)

**The finding:** Atticus Geiger, Christopher Potts, and collaborators at Stanford have built a rigorous framework — Causal Abstraction — that formally aligns high-level causal models with low-level neural network internals. The core method is *interchange interventions*: surgically swap a neural activation for what it would have been under a different input, then observe whether the model's behavior matches what the high-level causal model predicts. If it does, that activation *is* the causal variable. A 2025 survey found the method unifies activation patching, circuit analysis, causal scrubbing, sparse autoencoders, and concept erasure under a single theoretical framework. A March 2025 follow-up introduced *combining causal models* to get more accurate abstractions when a single model isn't enough.

**Why it's wild:** This gives a mathematically precise definition of what it means for an explanation to be *faithful* rather than just plausible. It does not just describe the model's behavior — it experimentally verifies causal claims about internals. Anthropic's attribution graphs (see below) are a direct industrial application of this work.

**Implication for Wizard:** The framework applies to engineering decisions, not just neural networks. A decision record is "faithful" only if you can demonstrate that removing one piece of the stated context would have changed the outcome. Wizard's decision notes should be designed to include at least one *load-bearing* constraint — the thing that, if removed, would flip the decision. That constraint is the causal variable. The rest is correlation.

**Sources:**
- [Causal Abstraction: A Theoretical Foundation for Mechanistic Interpretability (arXiv 2301.04709)](https://arxiv.org/abs/2301.04709)
- [Combining Causal Models for More Accurate Abstractions of Neural Networks (arXiv 2503.11429)](https://arxiv.org/abs/2503.11429)
- [Is Causal Abstraction Enough for Mechanistic Interpretability? (arXiv 2507.08802)](https://arxiv.org/pdf/2507.08802)

---

## 3. MAGMA: Orthogonal Causal, Temporal, Semantic, and Entity Memory Graphs (January 2026)

**The finding:** MAGMA (Multi-Graph Agentic Memory Architecture, arXiv 2601.03236) makes a clean architectural argument: existing memory systems entangle four distinct relational views — *semantic* (what things mean), *temporal* (when things happened), *causal* (what caused what), and *entity* (who/what was involved) — in a single vector store. This produces retrieval that cannot distinguish "these two facts are semantically similar" from "this fact caused that fact." MAGMA maintains four orthogonal relation graphs alongside a vector database, and treats retrieval as policy-guided traversal over whichever graph view is relevant to the query. Evaluated on LoCoMo and LongMemEval, it outperforms the current state-of-the-art in long-horizon reasoning.

**Why it's wild:** It formalizes the observation that "causal proximity" and "semantic similarity" are not the same thing, and that conflating them is the root cause of poor memory retrieval. The causal graph in MAGMA is explicitly separate from the semantic graph — a note that *caused* a decision is not necessarily *about* the same topic as the decision.

**Implication for Wizard:** Wizard's current synthesis model flattens everything into a single semantic embedding space. Under MAGMA's architecture, Wizard would maintain a parallel causal graph where edges represent "triggered," "constrained," "rejected because of," and "built on top of." A query like "what caused us to choose connection pooling?" would traverse the causal graph, not the semantic similarity index — giving a structurally different, more accurate answer.

**Sources:**
- [MAGMA: A Multi-Graph based Agentic Memory Architecture for AI Agents (arXiv 2601.03236)](https://arxiv.org/abs/2601.03236)
- [Graph-based Agent Memory: Taxonomy, Techniques, and Applications (arXiv 2602.05665)](https://arxiv.org/html/2602.05665v1)

---

## 4. Abduct, Act, Predict: Causal Failure Attribution in Multi-Agent Systems (September 2025)

**The finding:** The A2P framework (Abduct, Act, Predict, arXiv 2509.10401) transforms failure attribution from pattern recognition into structured causal inference. Given an agent trajectory, A2P guides an LLM through three steps within a single pass: *Abduction* — infer the hidden root causes behind an agent's actions; *Act* — define the minimal corrective intervention; *Prediction* — simulate the counterfactual trajectory to verify whether the intervention would have resolved the failure. This three-step structure produces a 2.85× improvement in step-level failure attribution accuracy over baselines that treat the problem as pattern matching over logs.

**Why it's wild:** Most post-hoc analysis tools just search for the proximate cause (what broke). A2P searches for the root cause *and* verifies it by simulating the world-without-the-error. It applies the standard causal inference pipeline — abduction, intervention, prediction — from Pearl's Ladder of Causation directly to agent debugging. The simulation step is what elevates it from correlation-finding to genuine causal verification.

**Implication for Wizard:** Engineering decisions fail and get revisited. When an engineer returns to a failed approach and wonders "why did we abandon this?", Wizard should be able to run the A2P reasoning: what was the root cause we abduced, what was the corrective intervention we proposed, and what did we predict would happen? These three fields — root_cause, intervention, predicted_outcome — are more useful than a free-text decision note. They are also mechanically extractable from session transcripts where the failure, the fix, and the verification are all recorded.

**Sources:**
- [Abduct, Act, Predict: Scaffolding Causal Inference for Automated Failure Attribution (arXiv 2509.10401)](https://arxiv.org/abs/2509.10401)
- [Counterfactual Forecasting of Human Behavior using Generative AI and Causal Graphs (arXiv 2511.07484)](https://arxiv.org/abs/2511.07484)

---

## 5. MACIE: Structural Causal Models + Shapley Values for Multi-Agent Attribution (November 2025)

**The finding:** MACIE (Multi-Agent Causal Intelligence Explainer, arXiv 2511.15716) combines Pearl's structural causal models, interventional counterfactuals, and Shapley values to answer: how much did each agent cause the collective outcome? The mechanism: generate counterfactual trajectories where each agent is individually replaced by a random baseline policy, then compare factual outcomes (all trained agents) against the counterfactual outcomes. Shapley values aggregate the individual contributions into a fair attribution score. The framework adds a natural-language narrative synthesis step that converts the causal attribution into human-readable explanations. Results show accurate outcome attribution with mean error <0.05 at 0.79 seconds per dataset.

**Why it's wild:** Shapley values were originally from cooperative game theory. Applying them via do-calculus counterfactuals to multi-agent trajectories is a genuinely novel synthesis. It gives a principled answer to "whose decision was the load-bearing one?" — something almost no existing system attempts.

**Implication for Wizard:** In a session where an engineer and AI assistant collaborate across multiple tool calls, MACIE's framing asks: which agent's action was causally decisive? This is directly applicable to Wizard's attribution problem. Rather than logging "the engineer decided X" or "Claude suggested Y," Wizard could compute a causal contribution score: "Claude's file-read on line 847 was the decisive input; the engineer's subsequent edit was a consequence, not an independent cause." This reframes note-taking from "who did what" to "what caused the outcome."

**Sources:**
- [MACIE: Multi-Agent Causal Intelligence Explainer for Collective Behavior Understanding (arXiv 2511.15716)](https://arxiv.org/abs/2511.15716)
- [Integrating Counterfactual Simulations with Language Models for Explaining Multi-Agent Behaviour (arXiv 2505.17801)](https://arxiv.org/abs/2505.17801)

---

## 6. CAM: Causality-Based Analysis of Multi-Agent Code Generation (February 2026)

**The finding:** CAM (Causality-Based Analysis Framework for Multi-Agent Code Generation Systems, arXiv 2602.02138) is the first framework that applies causal graph analysis to *code generation* specifically. It categorizes the intermediate outputs of multi-agent code generation pipelines and systematically constructs a causal graph over those outputs to prevent circular dependencies. Crucially, it uses LLMs as *counterfactual intervention engines* — prompting them to produce modified versions of real intermediate outputs that introduce plausible errors — and measures downstream effect. This reveals two findings: (1) context-dependent features whose importance only emerges through interaction with other features, and (2) the top-3 importance-ranked features can explain 73.3% of failures.

**Why it's wild:** CAM applies causal graph analysis not to agent memory but to the *product of agent work* — the code. It asks: which intermediate reasoning step in the code generation process was causally responsible for the final pass/fail? This is the engineering decision provenance question, applied directly to code.

**Implication for Wizard:** Every code change an engineer makes during a session has upstream causes in the session's decision tree. CAM's approach suggests Wizard could build a lightweight causal graph over session actions: which note, which search result, which task state transition was the proximate cause of a file edit? The "importance-ranked features" idea maps to Wizard's most valuable capability: surfacing the two or three session events that actually drove the outcome, rather than dumping the full transcript.

**Sources:**
- [CAM: A Causality-based Analysis Framework for Multi-Agent Code Generation Systems (arXiv 2602.02138)](https://arxiv.org/abs/2602.02138)
- [CausalAgent: A Conversational Multi-Agent System for End-to-End Causal Inference (arXiv 2602.11527)](https://arxiv.org/html/2602.11527v1)

---

## 7. PROV-AGENT: Formal Provenance for Agentic Workflows via W3C PROV + MCP (August 2025)

**The finding:** PROV-AGENT (arXiv 2508.02866, IEEE e-Science 2025) extends the W3C PROV standard specifically for agentic workflows. W3C PROV has three primitives: **Entity** (the artifact), **Activity** (the process), and **Agent** (the actor). PROV-AGENT adds agent-centric metadata — prompts, responses, decisions — and integrates with the Model Context Protocol (MCP) to capture provenance in near-real-time across edge, cloud, and HPC deployments. The critical design principle: provenance is generated *at decision time* via MCP instrumentation, not reconstructed from logs post-hoc. Companion work at arXiv 2509.13978 provides a reference architecture for interactive workflow provenance with LLM agents.

**Why it's wild:** PROV-AGENT is the first system that uses MCP — the exact protocol Wizard uses — as the provenance capture mechanism. The paper was published in the same quarter Wizard was being built. It is not theoretical: it runs across three different computing environments and captures real agentic workflow provenance.

**Implication for Wizard:** Wizard is already an MCP server. PROV-AGENT's architecture is a near-exact match: MCP tool calls are the Activity layer, session notes are the Entity layer, and the engineer + Claude are Agents. Adopting PROV-O vocabulary (`prov:wasGeneratedBy`, `prov:wasInfluencedBy`, `prov:wasDerivedFrom`) for Wizard's internal note relations would make decision records formally interoperable, queryable via SPARQL, and compatible with every W3C PROV-aware tool. The biggest lift: capturing `prov:wasInfluencedBy` edges at the time a note is saved, not inferred later.

**Sources:**
- [PROV-AGENT: Unified Provenance for Tracking AI Agent Interactions in Agentic Workflows (arXiv 2508.02866)](https://arxiv.org/abs/2508.02866)
- [LLM Agents for Interactive Workflow Provenance: Reference Architecture and Evaluation Methodology (arXiv 2509.13978)](https://arxiv.org/html/2509.13978v2)
- [PROV-O: The PROV Ontology (W3C)](https://www.w3.org/TR/prov-o/)

---

## 8. Causal Reinforcement Learning: Engineering Sessions as Trajectories with Extractable Causal Structure

**The finding:** Elias Bareinboim's Causal Reinforcement Learning (CRL) framework treats agent decisions as *interventions* in Pearl's do-calculus sense: an action is not merely correlated with outcomes, it *causes* them. Counterfactually-Guided Causal RL (CGC-RL) uses observational trajectory data to identify the counterfactual sequence that *would have* best completed a task. A 2025 survey in IEEE TNNLS covers the full CRL landscape. A parallel result: causal world models in offline RL (2025) show that causal structure is recoverable from trajectories — sequences of actions and observations — without requiring explicit annotation.

**Why it's wild:** Causal structure does not require the agent to narrate it. It is encoded in the *trajectory* — the sequence of actions and the outcomes that followed. This eliminates the dependency on a human or AI to explain their reasoning: the reasoning is implicit in what they tried, what failed, and what they tried next.

**Implication for Wizard:** Engineering work sessions are trajectories. Each tool call, file edit, and test run is an action with an observable outcome. CRL suggests that decision rationale can be *inferred* from the action-outcome sequence rather than requiring the engineer to articulate it. If the session transcript records "tried approach X → test failed → tried approach Y → test passed," the causal structure (X was ruled out because it caused test failures) is implicit. Wizard's synthesis step could extract this causal graph automatically, without relying on the engineer to narrate it.

**Sources:**
- [Causal Reinforcement Learning (Bareinboim Lab)](https://crl.causalai.net/)
- [An Introduction to Causal Reinforcement Learning (Bareinboim, arXiv)](https://causalai.net/r65.pdf)
- [Counterfactually-Guided Causal Reinforcement Learning with Reward Machines (NSF)](https://par.nsf.gov/servlets/purl/10580892)

---

## Cross-Cutting Themes

**1. The capture-time problem.** Across PROV-AGENT, clinical AI, CRL, and ADR research, the same finding: provenance must be captured *during* the decision, not reconstructed afterward. Post-hoc reconstruction produces rationalization, not causation. Wizard must move closer to the decision moment — ideally instrumenting the MCP tool-call stream rather than relying on retrospective notes.

**2. Rejected alternatives are the most valuable and most absent field.** MACIE's counterfactual trajectories, CAM's counterfactual interventions, and A2P's abduction step all converge on the same thing: the "why not X" is more durable than the "why Y" because it encodes the constraint landscape. In existing Wizard notes, this field is either empty or conflated with free-text rationale.

**3. CoT is not the causal record; trajectories are.** The Oxford faithfulness work and Geiger et al.'s causal abstraction framework both establish that verbal explanations are stories retrofitted onto computation. The actual causal record is the action-outcome trajectory (CRL lens) or the internal activation graph (Anthropic lens). For Wizard, this means trusting structured tool-call sequences over free-text rationale fields.

**4. Separate the four relational views.** MAGMA's core insight applies beyond agent memory: semantic similarity, temporal order, causal dependence, and entity co-occurrence are orthogonal relations. A Wizard query like "what caused us to adopt approach X?" is a *causal* query, not a semantic one. Answering it with vector similarity search will return thematically related notes, not causally upstream ones. Maintaining a lightweight causal edge layer alongside the semantic index is the architectural change needed.

**5. MCP is already the provenance capture layer.** PROV-AGENT's result is striking: the Model Context Protocol, which Wizard already uses, is sufficient infrastructure for formal W3C PROV provenance capture. No new transport or integration is needed — only instrumentation of the existing tool-call stream to emit PROV-O typed edges. The vocabulary (`wasGeneratedBy`, `wasInfluencedBy`, `wasDerivedFrom`) already covers the decision relations Wizard needs to store.
