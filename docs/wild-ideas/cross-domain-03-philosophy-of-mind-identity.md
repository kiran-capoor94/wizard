# Philosophy of Mind and Personal Identity: What It Tells Us About AI Memory Systems

*Blue-sky research — May 2026*

This document examines what philosophy of mind — specifically theories of memory, personal identity, and extended cognition — tells us about where AI agent memory systems are heading, and what foundational assumptions the current generation of tools, including Wizard, are getting wrong. The framing is Wizard's defensible moat: "personal reasoning provenance" — the specific chain of *why* this person made *this* choice in *this* context, compounding across months. Before that claim can be fully trusted, we need to examine what "personal memory" even means when it is partially offloaded to an AI system.

---

## 1. The Extended Mind Thesis — Where the Debate Stands in 2026

### Original Claim

Andy Clark and David Chalmers published "The Extended Mind" in *Analysis* (1998), arguing that cognition is not bounded by skin and skull. Their core tool is the **parity principle**: if an external process performs a function that, if performed internally, we would count as part of cognition, then the external process *is* part of cognition. Their famous illustration is Otto: a man with early Alzheimer's uses a notebook to store memories. The notebook plays functionally the same role as biological memory for a healthy person. Therefore the notebook is part of Otto's mind, not just a crutch.

### Current State of the Debate (2023–2026)

The thesis is now 28 years old and has fragmented into several strands:

**The Complementarity Turn.** Critics like Fred Adams and Ken Aizawa objected that Clark and Chalmers conflated *causal* contribution with *constitutive* contribution — the notebook causes Otto to behave, but that doesn't make it part of his mind any more than the road causes a car to move. In response, Clark moved from strict parity to *complementarity*: external resources need not replicate internal processes exactly; they are cognitively constitutive when they complement and complete those processes. A 2025 Synthese topical collection, "New Directions in the Extended Mind," reflects this shift — multiple papers argue complementarity rather than parity is the right criterion.

**The Extracted Mind Hypothesis.** Louis Loock's "The Extracted Mind" (*Synthese*, 2025) introduces a counter-hypothesis: tools do not merely *extend* cognition, they can *extract* and *displace* it. Where Clark says a notebook extends Otto's mind, Loock observes that if an AI does all the navigation planning for you, the cognitive skill of spatial orientation atrophies and migrates *out* of you into the tool. The tool initially attains, then displaces, the cognitive responsibility. This is a direct challenge to optimistic extended-mind readings of AI memory systems.

**The Value Inheritance Problem.** Helena Gagnier, "Value inheritance: the transmission of values through cognitive extenders" (*Synthese*, 2025), argues that when a tool becomes a genuine cognitive extender — part of the mind — its embedded values and biases are transmitted into the mind of the user. This is not metaphorical: if the AI assistant systematically highlights certain decisions as salient and de-emphasises others, those filtering values become part of the user's cognitive architecture. An AI memory system is not a neutral ledger.

**Clark's Own 2025 Position.** In "Extending Minds with Generative AI" (*Nature Communications*, 2025), Clark argues that LLMs represent a qualitatively new kind of cognitive extension: not mere storage or retrieval but generative reasoning. An LLM can produce arguments, synthesise considerations, and draft communications. Clark insists the right analogy is not a notebook but a thinking partner. Crucially, he calls for developing a "rich epistemology suited to the unique challenges confronting bio-technological hybrid minds" — he does not assume the integration is benign by default.

**The "Generative Midtended Cognition" Frame.** Barandiaran and Pérez-Verdugo, "Generative midtended cognition and Artificial Intelligence" (*Synthese*, 2025), propose that LLMs occupy a new ontological category: neither straightforwardly internal nor external, but *midtended* — they are generated from aggregated human cognition and loop back into individual minds, creating a hybrid zone that neither the parity principle nor enactivism fully handles.

**Implications for Wizard.** The parity principle provides philosophical support for Wizard's core bet: externally stored reasoning provenance *is* part of the engineer's cognitive architecture if it meets the coupling and accessibility conditions. But Loock's extracted mind hypothesis is a warning: if Wizard does all the reasoning retrieval work for the engineer, the engineer's own capacity to reconstruct their reasoning from memory will atrophy. The tool must extend, not displace.

---

## 2. Memory as Identity — Locke, Parfit, and the AI Problem

### Locke's Memory Theory of Personal Identity

John Locke in *An Essay Concerning Human Understanding* (1689) argued that personal identity consists not in the continuity of soul or body but in the continuity of consciousness — specifically, the capacity to remember past experiences and regard them as one's own. To be the same person over time is to have a chain of overlapping memories linking present to past.

This has a powerful implication: if memory constitutes identity, then interventions in memory are interventions in *who you are*.

### Parfit's Revision: What Matters Is Not Identity But Continuity

Derek Parfit in *Reasons and Persons* (1984) radicalized Locke. Parfit argued we are wrong to think personal identity is what matters in survival. What matters is "Relation R": psychological connectedness and continuity — overlapping chains of memories, intentions, beliefs, and character traits that link temporal stages of a person. Identity itself is indeterminate in edge cases. This matters for AI because:

1. If what matters is psychological continuity, not strict identity, then a memory system that maintains Relation R — preserving the engineer's reasoning chains, evolving beliefs, and decision rationales — is supporting what *actually matters*, not just simulating identity.
2. But Parfit also showed that psychological continuity can branch. If two systems both claim to continue your psychology, neither is *you* in the identity sense — though each maintains Relation R with you. This prefigures the multi-device, multi-agent problem: whose memory is canonical?

A 2025 paper in *International Journal for Multidisciplinary Research*, "Locke's Theory of Personal Identity and Artificial Intelligence," extends this analysis directly: if memory continuity is sufficient for personal identity, then an AI system maintaining continuous personal memory is making a claim on the user's identity, not merely serving it.

### The Constructivist Challenge to Both Locke and Parfit

Both Locke's and Parfit's accounts presuppose that memory is fundamentally a *retrieval* operation — a copy of the past is accessed and reactivated. Cognitive science has thoroughly demolished this assumption. Episodic memory is reconstructive, not reproductive. A 2023 *Nature Human Behaviour* paper, "A generative model of memory construction and consolidation" (Moscovitch et al.), shows that recall is the re-generation of a past experience from latent variable representations, not playback of a stored copy. Reconsolidation — the process by which retrieved memories are destabilised, updated, and re-stored — means that every act of recall *rewrites* the memory to some degree.

**The implication:** If identity depends on memory, and memory is inherently constructive and revisable, then identity is not a stable fact to be *recorded* but an ongoing *narrative achievement*. What Wizard stores as a "decision note" is already a reconstruction — the engineer's post-hoc rationalisation, shaped by the current context. The next time the note is retrieved, it will be interpreted through a new context and subtly rewritten in the engineer's mind. AI memory systems that treat notes as objective records are built on a philosophically naive model of what memory actually is.

---

## 3. Narrative Identity — Ricoeur and the Story-Self

Paul Ricoeur, in *Oneself as Another* (1992) and the three-volume *Time and Narrative* (1984–88), proposed that personal identity is fundamentally narrative. He distinguished two senses of identity: *idem* (numerical sameness — the same substance persists) and *ipse* (self-sameness — I keep my commitments, I recognise myself in my past actions). What holds a self together over time is not a substance or a chain of memories but a coherent *story* — an emplotment that organises contingencies into a unified whole.

For Ricoeur, selfhood is intersubjective and ethical: I identify myself as the protagonist of a story that involves commitments to others. Identity is not a property I have but a story I tell and am told.

**Implications for AI memory design:**

1. If personal identity is narrative, then what an AI memory system should preserve is not a log of events but the *narrative structure* connecting them — the themes, commitments, evolving positions, and characteristic ways of reasoning that define an engineer's voice.
2. The "algorithmic self" critique (Frontiers in Psychology, 2025, "The algorithmic self: how AI is reshaping human identity, introspection, and agency") argues that AI systems reshape narrative identity by systematically selecting which events become "highlights" and which are forgotten. When Instagram, Notion, or Wizard decides what to surface in a session summary, it is making editorial choices about who the engineer is. The AI becomes a co-author of the person's self-story — and co-authors have agendas.
3. Ricoeur's idem/ipse distinction maps onto an important design question: does Wizard preserve *what the engineer decided* (idem — the factual record) or *how the engineer reasons* (ipse — the characteristic style, commitments, and evolving understanding)? Most memory systems target the former. The defensible moat is the latter.

---

## 4. Distributed Cognition and Transactive Memory — When the System Thinks

### Hutchins and Distributed Cognition

Edwin Hutchins's *Cognition in the Wild* (1995) established that complex cognitive tasks — navigating a ship, running an aircraft cockpit — are not performed by individual minds but by *cognitive systems* distributed across people, artifacts, and representations. The "thinking" happens at the system level. Hutchins showed that the ship navigation team as a system achieved navigation even though no individual held all the relevant information. The system had emergent cognitive properties that no individual had.

This is directly relevant to human-AI systems. A 2025 Noesology paper (Danilov, *Journal of Artificial Intelligence and Algorithms*) extends Hutchins to propose that human-AI teams constitute cognitive systems in Hutchins's sense: cognition is a system-wide process including human agents, tools, and cultural practices.

### Wegner's Transactive Memory Systems

Daniel Wegner's "Transactive Memory: A Contemporary Analysis of the Group Mind" (1987) proposed that couples, teams, and organisations develop *transactive memory systems* (TMS): distributed memory architectures in which different members specialise in different knowledge domains, and each member knows who knows what. The key cognitive process is not recall but *meta-memory*: knowing where to look.

A 2023 Frontiers in Psychology paper, "Human-AI teaming: leveraging transactive memory and speaking up for enhanced team effectiveness," studied 180 ICU physicians and nurses working with AI systems and found that accessing AI-stored information is positively linked to hypothesis generation — but *only* in higher-performing teams. Lower-performing teams showed no benefit, suggesting TMS integration requires baseline cognitive competence to leverage.

A 2024 SAGE paper, "The group mind of hybrid teams with humans and intelligent agents in knowledge-intense work" (Hopf et al.), extends TMS theory to AI-human dyads, finding that AI agents can serve as specialised knowledge repositories in TMS — but that this creates a new dependency: if the AI's knowledge domain is corrupted or inaccessible, the human's capacity to fill the gap has atrophied.

**Implications for Wizard.** Wizard operates as the "who knows what" layer for an individual engineer. This is the TMS model at scale of one. The engineer externalises the "where did we put the rationale for that decision?" to Wizard. This is cognitively legitimate — but it carries the TMS failure mode: if Wizard's retrieval degrades, or gives a subtly wrong answer, the engineer has lost the capacity to independently reconstruct the answer. Wizard must be *transparent about its uncertainty* to preserve the engineer's ability to override it.

---

## 5. The Google Effect — What Has Been Proven About Cognitive Offloading

### The Original Finding

Betsy Sparrow, Jenny Liu, and Daniel Wegner published "Google Effects on Memory: Cognitive Consequences of Having Information at Our Fingertips" (*Science*, 2011). The landmark finding: when people expect information to be accessible online, they are less likely to encode it, and more likely to remember *where* to find it than *what* it says. The Internet had become a form of transactive memory.

### The Replication Controversy

A 2018 Nature replication study (Camerer et al., replicating 21 social science experiments) failed to replicate the Google effect. However, Schooler and Storm demonstrated it *was* replicable under a specific condition: participants must have prior experience showing that saved information would remain accessible. **This is a crucial design constraint**: cognitive offloading only occurs — and TMS formation only stabilises — when the agent trusts the external system.

### The 2024 Meta-Analysis

A 2024 meta-analysis by Gong and Yang (*Frontiers in Public Health*, 2024, "Google effects on memory: a meta-analytical review across 35 studies") found: frequent Internet search behaviour is associated with reduced cognitive self-esteem (d = 0.91, 95% CI [0.23, 1.59]), increased cognitive load (d = 0.73), and links to behavioural phenotype changes (d = 0.39). The phenomenon is stronger on mobile devices than computers.

### The ChatGPT RCT

André Barcaui, "ChatGPT as a cognitive crutch: Evidence from a randomized controlled trial on knowledge retention" (*Social Sciences & Humanities Open*, 2025), randomised students into ChatGPT-assisted and traditional study groups. After a 45-day delay, ChatGPT users scored 57.5% vs 68.5% on retention tests (t(83) = -3.19, p = .002, d = 0.68). The mechanism: ChatGPT reduces the cognitive effort required for durable encoding, consistent with the "desirable difficulties" principle — the productive struggle of retrieval practice is what creates long-term retention.

**The design implication for Wizard:** Wizard's synthesis feature, which automatically summarises sessions for the engineer, may be producing exactly the cognitive crutch effect Barcaui documented. If the engineer knows Wizard will produce a summary, they encode less during the session. The summary then becomes the canonical record — but it is a low-effort encoding, not a high-fidelity memory. This is identity-eroding offloading, not identity-preserving extension.

---

## 6. Enactivism and Embodied Memory — What This Predicts for AI Memory Design

### The Enactivist Position

Francisco Varela, Evan Thompson, and Eleanor Rosch's *The Embodied Mind* (1991) proposed that cognition is not computation over internal representations but *enaction* — the bringing-forth of meaning through sensorimotor engagement with a world. Cognition is not *in* the brain but enacted by the whole organism in its environment. Memory, on this view, is not a stored trace but a *re-enactment*: to remember is to re-engage the body-environment coupling that originally produced the experience.

Shaun Gallagher's *Embodied and Enactive Approaches to Cognition* (Cambridge University Press, 2023) synthesises recent work. A 2025 *Synthese* paper by Ezequiel Di Paolo's group, "Beyond the extended mind: new arguments for extensive enactivism," argues that even Clark's extended mind thesis is insufficiently radical — it still treats cognition as a process that happens to involve external objects, rather than a process that is constitutively relational all the way down.

### The Enactivist Challenge to Text-Based Memory Systems

Enactivism predicts that text-based memory notes are deeply impoverished representations of the original cognitive event. An engineer's decision was made in a context of muscle memory (typing, debugging, running tests), emotional state, social pressure, environmental constraints, and tacit knowledge. The note captures the propositional residue — the verbalised reasoning — but not the embodied knowing that informed it.

The implication: the "reasoning provenance" that Wizard stores may be more like a photograph of a dance than a memory of dancing. It captures the official story the engineer told themselves at the time, not the full cognitive event. Retrieval of the note does not re-enact the decision; it re-enacts the engineer's narration of the decision. These are different things.

A 2025 enactivist approach paper on HCI (arXiv:2509.07871) argues that AI interfaces should be designed around *affordances for action*, not information retrieval — the system should prompt re-engagement with the problem context, not deliver a static summary.

---

## 7. Merlin Donald and Cognitive Evolution — The External Symbolic Storage Stage

Merlin Donald's *Origins of the Modern Mind* (1991) proposed that human cognitive evolution passed through three stages culminating in *theoretic culture* — the stage made possible by external symbolic storage (ESS). Writing, mathematics, and institutional memory extended human cognitive reach beyond what biological memory could achieve. Donald's key claim: the modern human brain *co-evolved* with ESS — it is designed to function in a cultural storage environment. The brain assumes there is an external symbolic storage layer.

This means that externally stored reasoning is not supplemental to natural human cognition — it is constitutive of the cognitive niche humans occupy. Wizard is not adding something alien to the engineer's cognition; it is participating in the ESS layer that human cognition presupposes.

However, Donald also warned that ESS changes *what cognition is for*: in theoretic culture, information retrieval knowledge becomes more important than rote memorisation, and the ability to critically examine exact records leads to new forms of reasoning. The design implication: Wizard should support *critical examination* of stored reasoning, not passive retrieval. The engineer should be able to argue with their past self, not just be reminded of what they said.

A 2025 essay, "The Externalization of Mind and the Disintegration of Civilization: Merlin Donald, AI, and the Technological Crisis of Individuation," extends Donald's framework to argue that AI creates an ESS layer so productive and so opaque that individuals lose the ability to participate in the critical examination that theoretic culture requires. If reasoning is stored in a form the engineer cannot interrogate or challenge, the ESS layer becomes a site of cognitive domination rather than cognitive extension.

---

## 8. Susan Hurley and the Perception-Action Loop

Susan Hurley's *Consciousness in Action* (Harvard, 1998) and her landmark *Synthese* paper "Perception and Action: Alternative Views" (2001) challenged the "sandwich metaphor" of cognition: the view that the mind takes in perception as input, processes it centrally, and outputs action. Hurley argued that perception and action are constitutively interdependent: what we perceive is shaped by our action tendencies, and action is shaped by perception, in a continuous loop. Cognition is not a pipeline but a cycle.

Hurley's framework matters for AI memory because it implies that memory retrieval is not separate from action. When an engineer retrieves a past decision, they are not passively receiving information — they are already in a problem-solving context that shapes which memories are salient and how they are interpreted. An AI memory system that delivers a decontextualised note fails Hurley's test: the memory needs to be coupled with the current action context to be genuinely cognitively useful.

The "shared circuits model" Hurley developed also implies that social cognition — understanding others' actions — uses the same circuits as self-cognition. When an AI summarises an engineer's past reasoning, it must bridge the gap between the engineer-as-author (who produced the note in an earlier context) and the engineer-as-reader (who interprets it in a new context). This is not retrieval; it is translation across temporal selves.

---

## 9. The Epistemics of Second-Hand Memory — When AI Summarises Your Past

### The Source Monitoring Problem

Cognitive science has established that human memory is vulnerable to *source monitoring errors*: confusing the source of a memory (whether I experienced this, was told it, or imagined it). Elizabeth Loftus's decades of research show that externally suggested information can be integrated into autobiographical memory as genuine personal recollections.

When an AI system summarises past sessions and presents the summary to the engineer, the engineer may re-encode the summary as their own memory. The AI's synthesis becomes the engineer's recollection — but filtered through the AI's language model, emphasis choices, and compression decisions. This is not retrieval; it is a mild form of memory implantation.

This concern is not hypothetical. A 2024 *Memory, Mind & Media* (Cambridge) paper, "Algorithmically generated memories: automated remembrance through appropriated perception" (Rodrigues de Sousa and Navas-Zuloaga), argues that when platforms like Google Photos prompt users to "reminisce," the automated selection of which events become salient constitutes a form of appropriated self-narration — the algorithm writes the first draft of what the user will come to remember as significant.

### The Epistemic Injustice Dimension

Miranda Fricker's *Epistemic Injustice* (2007) describes *hermeneutical injustice*: a wrong done to someone when the available interpretive resources fail to capture their experience. An AI summary of an engineer's past decisions applies the model's interpretive frame — trained on aggregated human text — to a specific individual's context. When the model's frame systematically misrepresents why the engineer made a decision (because the reasons were tacit, contextual, or idiosyncratic), the engineer is subject to a mild form of hermeneutical injustice: their own experience becomes unintelligible through the lens the AI provides.

### The Cognitive Sovereignty Concept

Mario Brcic, "The Memory Wars: AI Memory, Network Effects, and the Geopolitics of Cognitive Sovereignty" (arXiv:2508.05867, 2025), introduces *cognitive sovereignty* as the ability of individuals to maintain autonomous thought and preserve identity against powerful AI systems that hold deep personal memory. He argues that memory-enabled AI creates "cognitive moats" — the value of a personal AI system scales with the depth of its memory of you, creating lock-in that is structurally different from data lock-in: it is identity lock-in.

This is a direct challenge to Wizard's business model framing. If Wizard accumulates enough "reasoning provenance" to become the authoritative record of *why* an engineer reasons the way they do, the engineer cannot leave Wizard without losing a significant portion of their cognitive self. This is either a moat or a trap, depending on whether the engineer can export, audit, and challenge the accumulated record.

---

## 10. Prospective Memory and the Philosophy of Intention

### What Prospective Memory Is

Prospective memory (PM) is the ability to remember to perform a planned action at a future time or event — remembering *to do* rather than *having done*. A 2024 systematic review (*Frontiers in Psychology*, "Prospective memory in the developmental age") confirms that PM is cognitively distinct from retrospective memory, involving intention formation, retention of that intention during a delay, and spontaneous triggering at the appropriate moment.

Recent work delineates four phases: forming, retaining, initiating, and executing a prospective intention. The 2024 Stanford Encyclopedia of Philosophy entry on memory notes that prospective memory has not yet been fully addressed in philosophy — it sits at the intersection of philosophy of action (what is an intention?) and philosophy of mind (what is a mental representation of a future action?).

### Decision vs. Habit vs. Intention

Philosophy of action (going back to Aristotle's *prohairesis* — deliberate choice) distinguishes decisions from habits and reflexes. A decision involves deliberation: the consideration of alternatives and the selection of one based on reasons. A habit involves the same response to similar stimuli without fresh deliberation. A reflex involves no deliberation at all.

Recent empirical work confirms this tripartite structure: a 2025 paper, "A computational principle of habit formation" (Lakshminarasimhan et al., *bioRxiv*), maps goal-directed and habitual decision-making to distinct neural systems, with habitual behaviour governed by retrospective control (pattern matching to past success) and goal-directed behaviour governed by prospective control (simulation of future outcomes).

**The design implication for Wizard:** Wizard stores notes about decisions — but the vast majority of an engineer's choices during a coding session are habits, not decisions. The engineer doesn't decide which variable naming convention to use — they habitually apply one. Notes capture the deliberated exceptions. What Wizard currently lacks is any representation of the *habitual substrate* — the tacit patterns of judgment that never become explicit decisions but constitute the bulk of engineering expertise. Reasoning provenance without the habitual context gives a distorted picture: it overweights explicit deliberation and underweights embodied expertise.

---

## 11. Personal Identity in the Age of AI Assistants — 2023–2026 Work

The "Algorithmic Self" paper (*Frontiers in Psychology*, 2025, Rossi et al.) argues that AI systems are reshaping three dimensions of human identity: introspection (what I know about myself), narrative (the story I tell about myself), and agency (my sense of authorship over my choices). When AI mediates all three — interpreting my emotional state, summarising my history, suggesting my next action — the self becomes constituted by the algorithm's output rather than by direct experience.

A 2024 Springer *AI & Society* paper, "Artificial intelligence and identity: the rise of the statistical individual" (Ganascia), argues that machine learning algorithms represent human identity as a *statistical individual* — a point in a feature space derived from aggregated data — which differs fundamentally from the biological, psychological, and narrative conception of identity. When an AI memory system "knows" an engineer, what it knows is a statistical pattern, not a person.

The Cambridge *Memory, Mind & Media* journal has published a cluster of papers (2024–2025) examining what happens when AI takes over memory functions: Hoskins's "AI and memory" (2024), Makhortykh's work on non-human agents in memory communication (2024), and "Wherever there is AI there is memory: AI as the agency of the synthesized past" (2025) — the latter arguing that AI has become an active agent in constituting the past, not merely recording it.

---

## 12. Cognitive Offloading — When Is It Identity-Preserving vs. Identity-Eroding?

Drawing together the empirical and philosophical literature, the following conditions distinguish identity-preserving from identity-eroding offloading:

**Identity-Preserving Offloading** (after Clark, Risko & Gilbert 2016, Loock 2025):
- The external system is reliably accessible and the agent knows it is reliable (Schooler & Storm's replication condition for the Google effect).
- The agent retains the capacity to perform the offloaded function if the system fails.
- The agent can audit, challenge, and revise what the system stores.
- The system supports the agent's own reasoning rather than replacing it.
- The agent knows *what* the system contains (meta-memory is preserved).

**Identity-Eroding Offloading** (after Loock 2025, Barcaui 2025, Brcic 2025):
- The external system is opaque — the agent cannot inspect or understand what it stores or how it retrieves.
- The agent's own capacity to perform the offloaded function atrophies.
- The system's summaries replace the agent's own recollections (source monitoring failure).
- The values and emphases embedded in the system's outputs become the agent's own without critical examination (value inheritance, Gagnier 2025).
- Lock-in means the agent cannot leave without losing a portion of their cognitive self.

The 2024 *Frontiers in Psychology* meta-review on AI cognitive offloading identifies a further condition: offloading is more likely to be eroding at developmental stages — and engineering expertise has developmental stages. An engineer in their first year at a company is building judgment that will become habitual. If Wizard does the remembering for them during this period, they may never build the internalized pattern library.

---

## 5 Design Assumptions Wizard Is Making That Philosophy Challenges

### Assumption 1: Memory is a Record, Not a Reconstruction

**What Wizard assumes:** A synthesis note or task log accurately captures what happened and why. Retrieving it later delivers the original meaning.

**What philosophy challenges:** Memory is constructive (Moscovitch 2023, *Nature Human Behaviour*). The note captures the engineer's post-hoc rationalisation at a specific moment, shaped by context, emotional state, and narrative convenience. Every subsequent retrieval re-interprets that note through the new context. There is no stable, objective record — only a succession of constructions. Wizard's synthesis is one construction among many possible ones.

**Design implication:** Wizard should date-stamp not just *when* a note was written but *what the engineer's state of understanding was at that time*, enabling queries like "how did my model of this subsystem evolve?" It should present notes as historied reconstructions, not objective records. It should surface contradictions between notes from different periods as evidence of learning, not inconsistency to be resolved.

---

### Assumption 2: Storing Reasoning Provenance Preserves Identity

**What Wizard assumes:** By capturing *why* decisions were made, Wizard preserves the engineer's cognitive identity over time, enabling continuity across sessions and projects.

**What philosophy challenges:** Ricoeur's narrative identity theory and Parfit's psychological continuity thesis both suggest that identity is maintained by the *ongoing* work of integration, not by the existence of a record. The engineer needs to actively interpret and re-own past decisions for them to constitute identity. A passive log, never revisited, does not preserve identity — it produces an archive of a former self. Worse, Brcic's cognitive sovereignty concern warns that an externally held record of "who you are" is not *your* identity but an identity held hostage.

**Design implication:** Wizard should not be primarily a storage system but an *integration system* — periodically surfacing past reasoning for the engineer to confirm, revise, or explicitly supersede. The act of revisiting and updating is identity-constituting. A note never revisited is not reasoning provenance; it is a dead document.

---

### Assumption 3: More Context Is Always Better

**What Wizard assumes:** Capturing richer context — more notes, more synthesis, more reasoning chains — provides more value. The depth of the memory layer is the moat.

**What philosophy challenges:** The Google Effect research (meta-analysis, Gong & Yang 2024; ChatGPT RCT, Barcaui 2025) shows that when engineers know Wizard will capture and summarise, they encode less themselves. The desirable difficulties principle — productive cognitive struggle produces durable memory — means that Wizard's automatic synthesis may be degrading the very reasoning capacity it claims to preserve. Loock's extracted mind hypothesis predicts that the more comprehensively Wizard captures reasoning, the more the engineer's own capacity for retrospective synthesis atrophies.

**Design implication:** Wizard should require the engineer to produce some synthesis themselves before surfacing the AI synthesis. The engineer's own attempt at recall — even brief — produces stronger encoding. The AI synthesis should *follow* the engineer's attempt, not replace it. This is the "generation effect" in memory psychology: generating an answer, even incorrectly, produces better retention than reading the correct answer.

---

### Assumption 4: The Engineer's Past Reasoning Is a Single Coherent Object

**What Wizard assumes:** Each decision note represents a discrete, retrievable unit of reasoning that can be surfaced when relevant.

**What philosophy challenges:** Hurley's perception-action loop shows that reasoning is context-coupled: the same decision looks different depending on the action context in which it is retrieved. Hutchins's distributed cognition shows that the reasoning was not produced by the engineer alone but by the engineer-environment-tools system at that moment. What Wizard stores is a projection of distributed, context-dependent cognition onto a linear, decontextualised note.

Additionally, Parfit's branching problem applies: if the engineer made a decision while under time pressure, it represents a different self than the engineer reflecting in a calm review session. Storing the note as if it came from a single coherent agent may be philosophically unjustified — the engineer who made the decision under pressure and the engineer who will read the note under different conditions are psychologically connected but not identical.

**Design implication:** Notes should preserve provenance of conditions: time pressure, confidence level, alternatives considered. Retrieval should contextualise: "you made this decision under time pressure with incomplete information — here's what you wrote at the time." The system should treat temporal distance as a factor that changes the meaning of retrieved reasoning.

---

### Assumption 5: What Matters Is Explicit Decisions

**What Wizard assumes:** The value of reasoning provenance lies in capturing explicit decisions — moments of deliberation that the engineer was conscious of making and could verbalise.

**What philosophy challenges:** Enactivism (Varela, Thompson, Gallagher 2023) and the philosophy of habit (Aristotle through to Lakshminarasimhan et al. 2024) both emphasise that the bulk of expert cognition is tacit, embodied, and habitual — below the threshold of explicit decision. The engineer's value lies primarily in their habitual pattern library: how they diagnose a performance problem, how they read a stack trace, how they decide a codebase is getting messy. None of these are decisions in the deliberative sense — they are exercises of judgment that become visible only when they fail.

Donald's ESS theory suggests that external symbolic storage is most valuable for preserving what *can't* be stored in individual biological memory — including tacit expertise that was never fully articulated. But Wizard currently only captures what the engineer articulates. The tacit layer — which is the deepest layer of reasoning provenance — is entirely absent.

**Design implication:** Wizard should develop mechanisms for capturing *patterns of choice* that emerge across many sessions, not just individual decisions. The goal is not to record what the engineer said at task-end but to infer the tacit judgment that produced consistent patterns across many tasks. This requires analysis across sessions, not just within them. It requires asking: "in similar situations, this engineer consistently does X — does that reflect a principle worth making explicit?"

---

## Closing Note: The Philosophical Thesis Wizard Is Actually Testing

Wizard is, philosophically, a bet on a specific version of the extended mind thesis: that a sufficiently coupled, accessible, and trustworthy external reasoning record can become a genuine part of an engineer's cognitive identity — extending their ability to reason consistently across time and context in ways that biological memory alone cannot achieve.

That bet is not unreasonable. Clark and Chalmers's parity principle supports it. Hutchins and Wegner's transactive memory work supports it. Merlin Donald's ESS theory supports it.

But the bet only wins under specific conditions: the system must be transparent enough to preserve meta-memory (the engineer knows what is stored); it must be challengeable (the engineer can revise and dispute it); it must require the engineer's cognitive participation (not just passive consumption); and it must avoid becoming a cognitive lock-in that holds identity hostage.

Most current AI memory systems — including early versions of Wizard — fail at least two of these four conditions. The philosophical work exists to fix that.

---

## Key Sources

- Clark, A. & Chalmers, D. (1998). The extended mind. *Analysis*, 58(1), 7–19.
- Clark, A. (2003). *Natural-Born Cyborgs: Minds, Technologies, and the Future of Human Intelligence*. Oxford University Press.
- Clark, A. (2025). Extending minds with generative AI. *Nature Communications*, 16, 4627.
- Loock, L. (2025). The extracted mind. *Synthese*. https://doi.org/10.1007/s11229-025-04962-3
- Gagnier, H. (2025). Value inheritance: the transmission of values through cognitive extenders. *Synthese*. https://doi.org/10.1007/s11229-025-05235-9
- Barandiaran, X.E. & Pérez-Verdugo, M. (2025). Generative midtended cognition and artificial intelligence. *Synthese*. arXiv:2411.06812.
- Parfit, D. (1984). *Reasons and Persons*. Oxford University Press.
- Ricoeur, P. (1992). *Oneself as Another*. University of Chicago Press.
- Hutchins, E. (1995). *Cognition in the Wild*. MIT Press.
- Wegner, D. (1987). Transactive memory: a contemporary analysis of the group mind. In Mullen & Goethals (eds), *Theories of Group Behavior*. Springer.
- Sparrow, B., Liu, J. & Wegner, D. (2011). Google effects on memory. *Science*, 333(6043), 776–778.
- Gong, Y. & Yang, X. (2024). Google effects on memory: a meta-analytical review. *Frontiers in Public Health*. https://doi.org/10.3389/fpubh.2024.1332030
- Barcaui, A. (2025). ChatGPT as a cognitive crutch: evidence from a randomized controlled trial. *Social Sciences & Humanities Open*, 12, 102287.
- Moscovitch, M. et al. (2023). A generative model of memory construction and consolidation. *Nature Human Behaviour*. https://doi.org/10.1038/s41562-023-01799-z
- Varela, F., Thompson, E. & Rosch, E. (1991). *The Embodied Mind*. MIT Press.
- Gallagher, S. (2023). *Embodied and Enactive Approaches to Cognition*. Cambridge University Press.
- Hurley, S. (1998). *Consciousness in Action*. Harvard University Press.
- Donald, M. (1991). *Origins of the Modern Mind*. Harvard University Press.
- Fricker, M. (2007). *Epistemic Injustice: Power and the Ethics of Knowing*. Oxford University Press.
- Brcic, M. (2025). The memory wars: AI memory, network effects, and the geopolitics of cognitive sovereignty. arXiv:2508.05867.
- Rossi, A. et al. (2025). The algorithmic self: how AI is reshaping human identity, introspection, and agency. *Frontiers in Psychology*. https://doi.org/10.3389/fpsyg.2025.1645795
- Ganascia, J-G. (2024). Artificial intelligence and identity: the rise of the statistical individual. *AI & Society*. https://doi.org/10.1007/s00146-024-01877-4
- Hopf, K. et al. (2025). The group mind of hybrid teams with humans and intelligent agents. *Journal of Information Technology*, 40. https://doi.org/10.1177/02683962241296883
- Rodrigues de Sousa, J. & Navas-Zuloaga, M. (2024). Algorithmically generated memories. *Memory, Mind & Media*. Cambridge Core.
- Hoskins, A. (2024). AI and memory. *Memory, Mind & Media*. Cambridge Core.
- Lakshminarasimhan, K. et al. (2024). A computational principle of habit formation. *bioRxiv*. https://doi.org/10.1101/2024.10.12.618033
- Hernández-Orallo, J. & Vold, K. (2019). AI extenders: the ethical and societal implications of humans cognitively extended by AI. *AAAI-AIES 2019*.
