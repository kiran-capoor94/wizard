# Wild Ideas: Embodied Cognition and Ambient Context for Wizard

**Date:** 2026-05-02  
**Question:** What could Wizard unlock if it had genuine environmental awareness — not just what the agent tells it, but what it can infer from observable signals in the world?

---

## The Core Problem

Wizard currently knows only what a Claude agent explicitly writes into it. It has no awareness of:

- What files are open in the IDE right now
- Whether the engineer is in a deep focus state or thrashing between tabs
- What just changed in git
- What time of day it is, or how long this session has actually run
- Whether the engineer returned from a break or just context-switched
- What the working directory looks like, or what tests just failed

This means Wizard's memory is entirely declarative — it only captures what people choose to say aloud. But most of what makes a task hard, most of the tacit knowledge about a codebase, and most of the context that determines whether a note is useful — is never said aloud at all. It lives in the environment.

The research below suggests this is not just a product gap. It touches on a deep question in cognitive science: where does thinking happen?

---

## Idea 1: The Extended Mind — Your IDE as a Cognitive Organ

**The research:** Andy Clark and David Chalmers' 1998 paper ["The Extended Mind"](https://www.alice.id.tue.nl/references/clark-chalmers-1998.pdf) argues that cognition doesn't stop at the skin. Objects in the external environment — a notebook, a whiteboard, a computer — can be genuine parts of a cognitive process, not merely inputs to one. Clark calls these "cognitive niche constructions": environments we scaffold to extend our reach beyond the "ancient fortress of skin and skull."

**The wild idea:** A software engineer's IDE is a cognitive organ. The set of open files, the split-pane arrangement, the pinned tabs — these are not just windows. They are the current working memory of the developer's mind, externalised. The spatial layout of the editor *is* the structure of the thought.

Wizard could treat the IDE's file-open state as a first-class signal. When a session starts or resumes, Wizard could ingest: which files are open, which is focused, what was recently edited, what tests were last run. This is not instrumentation for its own sake — it's reading the shape of the engineer's mind at the moment of engagement.

Implication: session notes anchored to specific open-file states would become dramatically more useful. "What were you thinking when `repositories.py` and `services.py` were open side-by-side?" is a question Wizard could actually answer.

**Sources:**
- [The Extended Mind (Clark & Chalmers, 1998)](https://www.alice.id.tue.nl/references/clark-chalmers-1998.pdf)
- [Extended Mind Thesis — Wikipedia](https://en.wikipedia.org/wiki/Extended_mind_thesis)
- [Andy Clark, Language, embodiment, and the cognitive niche — PhilPapers](https://philpapers.org/rec/CLALEA-3)

---

## Idea 2: Context-Dependent Memory — Returning to the Scene of the Crime

**The research:** Context-dependent memory is one of the most robust findings in cognitive psychology: memory retrieval improves dramatically when the retrieval context matches the encoding context. Godden and Baddeley (1975) famously showed that divers who learned word lists underwater recalled them better underwater. The brain encodes not just content but the *gestalt* of the situation — time of day, location, emotional state, ambient environment. A [2024 meta-analysis](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2024.1489039/full) confirms frequency and dwell time in a context also modulate retrieval strength.

**The wild idea:** When Wizard stores a note, it could automatically tag environmental context metadata: time of day, day of week, current git branch, the set of open files, whether tests are passing. When the engineer later returns to a similar context — same branch, same files open — Wizard could surface notes from past sessions with matching context signatures, unprompted.

This is context reinstatement as a feature, not a metaphor. The engineer doesn't need to search for past notes about `auth_service.py` — when they open `auth_service.py`, Wizard already knows what it knows about that file, from every prior session where it was the focus.

Implication: Wizard becomes less of a search tool and more of a spatial memory system. The workspace *triggers* recall the same way returning to a room triggers what you went there for.

**Sources:**
- [Context-dependent memory — Wikipedia](https://en.wikipedia.org/wiki/Context-dependent_memory)
- [Context-Dependent Memory in the real world (Frontiers, 2024)](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2024.1489039/full)
- [Neurofeedback and context reinstatement — PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC7034791/)

---

## Idea 3: Git as an Emotional Signal — Mining the Commit Stream

**The research:** A well-established line of MSR (Mining Software Repositories) research has shown that git commit messages encode emotional state. Guzman et al.'s [2014 empirical study](https://dl.acm.org/doi/10.1145/2597073.2597118) at MSR found measurable sentiment patterns: commits made on Mondays trend negative, distributed teams trend positive, high-volume committers express more frustration. A 2025 study using LLM-based augmentation achieved 97%+ precision on a four-label scheme: Satisfaction, Frustration, Caution, and Neutral.

Beyond sentiment: git activity itself carries signal. A burst of micro-commits on the same file suggests thrashing. A long gap followed by a large diff suggests a breakthrough. A revert suggests a wrong turn. A new branch name can suggest intent ("fix/auth-regression" vs "explore/new-caching-approach"). A 2024 open-source tool called `code996` takes this further: it maps commit timestamps to work-life balance signals, detecting when engineers are consistently committing at 01:00 and inferring burnout risk — currently 51% of developers in the 2024 Stack Overflow survey self-report burnout, and git history offers an earlier-leading indicator than any survey.

**The wild idea:** Wizard could watch the git log as a passive stream and infer task state from it — without the engineer saying a word. A pattern of thrashing (10 commits in 2 hours, all touching the same 3 lines) could automatically trigger a note: "You seem stuck on this. What have you tried?" A clean merge to main could mark task completion. A first commit to a new branch could start a new task context automatically.

This transforms git from an artifact store into a low-latency signal of cognitive state — the closest thing to a heartbeat monitor for the engineering mind.

**Sources:**
- [Sentiment analysis of commit comments in GitHub (ACM, 2014)](https://dl.acm.org/doi/10.1145/2597073.2597118)
- [Exploring Expressions of Emotions in GitHub Commit Messages](https://geeksta.net/geeklog/exploring-expressions-emotions-github-commit-messages/)
- [Improving Developer Emotion Classification via LLM-Based Augmentation (2025)](https://openreview.net/forum?id=FPLNSx1jmL)
- [Building a Burnout Detector: Analyzing Git Commit Patterns with Python & Scikit-learn (WellAlly, 2024)](https://www.wellally.tech/blog/build-burnout-detector-python-git)

---

## Idea 4: The Dangling String — Calm Technology for Cognitive Load

**The research:** Mark Weiser and John Seely Brown's ["Designing Calm Technology" (1995)](https://calmtech.com/papers/designing-calm-technology.html) introduced the idea of systems that live in the periphery of attention — informing without demanding. Their canonical example was Natalie Jeremijenko's "Dangling String": a strip of plastic spaghetti connected to an Ethernet cable via a small motor. Busy network traffic made it whirl; a quiet network left it still. No screen, no alert, no decision required. The peripheral nervous system processed it automatically.

The core principle: the periphery can hold far more attentional bandwidth than the fovea. Weiser argued that truly calm technology would move information fluidly between centre and periphery, only pulling things to centre-stage when they needed a decision.

**The wild idea:** Wizard could maintain a "cognitive load halo" — an ambient signal, not an explicit alert — that reflects the inferred state of the session. Not a dashboard. Not a notification. Something peripheral: a subtle change in the IDE sidebar colour, or a quiet field in the status bar showing "deep focus / 47 min" vs "thrashing / context switched 8 times in 20 min."

The point is not to surface data — it is to externalize the engineer's own state back to them without demanding they look at it. This is Weiser's insight applied to self-awareness: the system knows things the engineer doesn't consciously track, and it reflects them back calmly.

**Sources:**
- [Designing Calm Technology — Weiser & Brown (1995)](https://calmtech.com/papers/designing-calm-technology.html)
- [Ambient Awareness — Calm Technology (ebrary)](https://ebrary.net/99114/computer_science/ambient_awareness)
- [Calm Technology and the Dangling String (Medium)](https://medium.com/digitalshroud/calm-technology-and-the-dangling-string-e94fcbc9db8e)

---

## Idea 5: Flow State as an Inferrable Signal — Protect What's Fragile

**The research:** IEEE Software research has demonstrated the ability to [predict developer cognitive and emotional states in real-time using biometrics](https://ieeexplore.ieee.org/document/7476774/) — EDA (electrodermal activity) sensors and respiratory rate can identify when a developer is "in flow" vs. experiencing difficulty or frustration. The research by Müller et al. showed accurate predictions are possible over multiple days in natural work environments.

A striking 2024 PLOS One study ([EEG as a potential ground truth for the assessment of cognitive state in software development activities](https://pmc.ncbi.nlm.nih.gov/articles/PMC10919648/)) took 21 programmers, equipped them with simultaneous EEG, ECG, EDA, eye-tracking, and fMRI, and ran them through real code inspection tasks. The core finding: EEG theta/alpha/beta waves reliably distinguish low, medium, and high cognitive load during code comprehension — and they identified which specific EEG channels (frontal and parietal) gave the highest discriminative power, pointing toward a dry-electrode wearable headband as a practical field deployment. The paper's deeper conclusion is that cognitive load in programming saturates before software complexity metrics indicate it — the engineer's brain is overloaded well before cyclomatic complexity registers anything interesting.

But biometrics are invasive. What's more tractable is behavioural flow inference. Gloria Mark's [23-minute recovery research](https://contextkeeper.io/blog/the-real-cost-of-an-interruption-and-context-switching/) shows that interruptions are catastrophically expensive for developers because they break complex mental models. PanDev Metrics already tracks IDE heartbeat data to detect project and language switches. RescueTime's analysis shows developers achieve only 2h48m of actual focused work daily.

**The wild idea:** Wizard doesn't need a heart-rate monitor to infer flow. It needs only: time-since-last-context-switch, edit velocity on a single file, test run frequency, and whether the engineer is on the same git branch they were 20 minutes ago. A continuous unbroken session with high edit velocity in a tight file cluster is a strong signal of deep work. Wizard could treat this as protected state — suppressing non-urgent notes, deferring synthesis, not prompting.

The inverse is equally powerful: rapid context switching (back to Jira, then Slack, then back to the IDE) could signal a blocked state, and Wizard could surface the most recent `investigation` note as an aide-mémoire when the engineer returns.

The 2026 horizon: affordable EEG headbands (Muse, Dreem, and forthcoming "headphone EEG" — see [Advancing Wearable BCI: Headphone EEG for Cognitive Load Detection in Lab and Field, IMWUT 2024](https://dl.acm.org/doi/abs/10.1145/3712283)) may make non-invasive biometric flow detection commercially viable as an optional Wizard input. A single bit — "deep focus active: yes/no" — would be enough.

**Sources:**
- [Leveraging Biometric Data to Boost Software Developer Productivity (IEEE, 2016)](https://ieeexplore.ieee.org/document/7476774/)
- [EEG as a potential ground truth for programmer cognitive state (PLOS One, 2024)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10919648/)
- [Advancing Wearable BCI: Headphone EEG for Cognitive Load Detection (IMWUT, 2024)](https://dl.acm.org/doi/abs/10.1145/3712283)
- [The Real Cost of Interruption and Context Switching — ContextKeeper](https://contextkeeper.io/blog/the-real-cost-of-an-interruption-and-context-switching/)
- [Context Switching Kills Developer Productivity — PanDev Metrics](https://pandev-metrics.com/docs/blog/context-switching-kills-productivity)

---

## Idea 6: Cognitive Offloading — The Google Effect Turned Into a Feature

**The research:** Cognitive offloading is the use of physical action or external tools to reduce in-head cognitive load — from tilting your head to read rotated text, to writing a to-do list. Risko & Gilbert's [foundational review (2016)](https://www.sciencedirect.com/science/article/abs/pii/S1364661316300985) established the field. A striking finding: people preferentially offload *high-value* items — the things they most want to remember are the things they're most likely to write down. There is also a well-replicated "Google effect": knowing you can look something up causes your brain to invest less in encoding it internally. Betsy Sparrow's research showed that people remember *where* to find information better than the information itself when they know it's stored.

**The wild idea:** This is a design constraint for Wizard, not just an insight. If engineers know Wizard captures context, they will stop encoding it themselves — the Google effect guarantees it. This is only a problem if Wizard's retrieval is slow or unreliable. If retrieval is instant and contextually triggered (see Idea 2), the offloading becomes net-positive: the engineer carries less cognitive debt and can allocate attention to harder problems.

But here's the wild extension: what if Wizard *deliberately modelled what the engineer has offloaded to it* — maintaining a live "working memory complement" that tracks what is in Wizard but not in the engineer's head? The system could proactively resurface things the engineer is statistically likely to have forgotten, based on time since encoding and the recency of related context. This is spaced repetition, but event-triggered rather than time-triggered.

**Sources:**
- [Cognitive Offloading — ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1364661316300985)
- [Consequences of Cognitive Offloading — PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC8358584/)
- [Cognitive Offloading is Value-Based Decision Making (2024)](https://www.sciencedirect.com/science/article/pii/S0010027724000696)
- [Outsourcing Memory to External Tools: A Review of Intention Offloading — PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC9971128/)

---

## Idea 7: MyLifeBits and the Failure Mode of Passive Capture

**The research:** Gordon Bell's [MyLifeBits project (2001–present)](https://www.microsoft.com/en-us/research/project/mylifebits/) was the most ambitious lifelogging experiment ever conducted. Bell wore two cameras, captured every website, every email, every phone call, every document. He generated 1 GB/month of raw life data. The goal was a surrogate memory — a searchable externalisation of everything. It inspired a generation of lifelogging startups.

It mostly failed to deliver, for a [striking reason](https://machinesociety.ai/p/forget-about-prosthetic-memory-lifelogging-is-dead): captured data without structure is retrieval noise, not memory. Bell rarely used his own archive. The bottleneck was never capture — it was meaning. A photo of a whiteboard is not a decision. A transcript of a standup is not a task. Passive capture at massive scale produces an undifferentiated haystack.

The story resurfaced dramatically in May 2024 when Microsoft announced [Windows Recall](https://support.microsoft.com/en-us/windows/privacy-and-control-over-your-recall-experience-d404f672-7647-41e5-886c-a3c59680af15) — a feature that screenshots the user's screen every few seconds and makes the history searchable via natural language. Security researchers immediately demonstrated that early versions stored sensitive data in unencrypted plain text. The feature has been delayed twice, re-launched as opt-in in April 2025, and as of 2026 still attracts security red flags. Microsoft's Recall is the first major consumer product to attempt Bush's Memex vision. Its troubled rollout is a live case study in the privacy-trust failure mode of total passive capture.

Meanwhile, [Screenpipe](https://screenpi.pe/) — an open-source, fully local alternative — took the opposite bet: MIT-licensed, no cloud, all OCR and Whisper transcription on-device, with a plugin ("Pipe") architecture to route captured data into tools of your choosing. It reached commercial relevance as a Rewind/Recall alternative for developers who reject cloud-dependent surveillance. By 2026 it had become the reference implementation for local-first passive screen memory.

**The wild idea:** The lesson for Wizard is a design constraint and an opportunity. Wizard must not become MyLifeBits. The correct architecture is *selective passive capture* — a narrow set of high-signal behavioural observables (git branch, open files, test results, session duration, edit velocity) combined with the LLM's ability to synthesize meaning from them. The signal:noise ratio is the product's core invariant.

The flip side is that MyLifeBits pointed at something real: Vannevar Bush's 1945 Memex vision of an "intimate supplement to memory" is now technologically tractable for the first time. The ingredients are there. The question is what *not* to capture. Screenpipe's open-source approach suggests a specific Wizard integration path: a minimal local Pipe that watches only for engineering signals (test runner output, git events, IDE window focus changes) rather than total-recall screen history — capturing the semantics of developer activity without becoming a surveillance tool.

**Sources:**
- [MyLifeBits — Microsoft Research](https://www.microsoft.com/en-us/research/project/mylifebits/)
- [MyLifeBits: a personal database for everything (ACM CACM, 2006)](https://dl.acm.org/doi/10.1145/1107458.1107460)
- [Forget about prosthetic memory. Lifelogging, ironically, is dead!](https://machinesociety.ai/p/forget-about-prosthetic-memory-lifelogging-is-dead)
- [Microsoft Windows Recall — Privacy and control (2025)](https://support.microsoft.com/en-us/windows/privacy-and-control-over-your-recall-experience-d404f672-7647-41e5-886c-a3c59680af15)
- [One year after its rocky launch, Microsoft's Windows Recall still raises security red flags (GeekWire, 2026)](https://www.geekwire.com/2026/one-year-after-its-rocky-launch-microsofts-windows-recall-still-raises-security-red-flags/)
- [Screenpipe — open-source local AI screen memory](https://screenpi.pe/)
- [Lifelogging as Extreme Personal Information Management (arXiv 2024)](https://arxiv.org/html/2401.05767)

---

## Idea 8: Prospective Memory and the Interrupted Task — AR as the Model

**The research:** Prospective memory is the cognitive system responsible for remembering to do things in the future. It is notoriously unreliable after interruptions. A [2024 CHI paper](https://dl.acm.org/doi/10.1145/3613904.3642666) showed that augmented reality cues placed at the interruption point dramatically reduced both resumption time and resumption errors — because they reinstated the *task context* spatially, at exactly the moment the engineer returned to their physical station.

The key insight: prospective memory failures are not about forgetting. They are about the absence of a cue at the moment of return. The engineer knew what they were doing; they just had no environmental signal to trigger retrieval when they came back.

**The wild idea:** Wizard could implement a lightweight version of this without AR. When a session is interrupted (editor closed, machine locked, long gap in git activity), Wizard logs a "last-state snapshot" — the open files, the current task, the last note, the last test result. On session resumption, it presents this snapshot as the first thing, before any new context is surfaced. Not a summary. A reinstatement cue.

This is the difference between "here's what you've been working on" (a summary that requires reading) and "here's where you were standing when you stopped" (a cue that triggers retrieval). The second is what AR achieves physically; Wizard can approximate it digitally.

**Sources:**
- [AR Cues Facilitate Task Resumption after Interruptions (CHI 2024)](https://dl.acm.org/doi/10.1145/3613904.3642666)
- [Interruptions Create Prospective Memory Tasks (ResearchGate)](https://www.researchgate.net/publication/227643114_Interruptions_Create_Prospective_Memory_Tasks)
- [MEMOS: Distributed processing of reminding tasks (Springer)](https://link.springer.com/article/10.1007/s00779-004-0332-5)

---

## Idea 9: Tacit Knowledge Elicitation via Conversational Scaffolding

**The research:** Tacit knowledge — the know-how that experts can't fully articulate — is the central problem of knowledge management. A [2025 paper](https://arxiv.org/html/2507.03811v1) describes using LLM agents to iteratively reconstruct dataset descriptions through dialogue with employees: not capturing what they say, but using conversational probing to surface what they didn't know they knew. A [2024 UIST adjunct paper](https://dl.acm.org/doi/10.1145/3746058.3758467) extends this to creative domains.

The fundamental problem is that tacit knowledge is non-declarative — it cannot be extracted by asking "what do you know?" It can only be extracted by observing behaviour and asking targeted questions about anomalies in that behaviour. "Why did you open that file before running tests?" reveals something that no explicit note would capture.

**The wild idea:** Wizard could implement a lightweight "tacit knowledge interview" pattern triggered by behavioural anomalies. If the engineer navigates to a file, immediately closes it, and navigates elsewhere — a pattern that suggests "I know something about that file" — Wizard could ask: "You opened `legacy_auth.py` briefly. Any context worth saving?" Not a constant prompt. A targeted, behavioural-anomaly-triggered question.

This is the inverse of passive capture: it uses observable action as a hypothesis about knowledge state, and uses a question to confirm or refute that hypothesis. The LLM is doing inference, not summarisation — which is exactly the right use of LLM capability.

**Sources:**
- [Leveraging LLMs for Tacit Knowledge Discovery in Organizational Contexts (arXiv 2025)](https://arxiv.org/html/2507.03811v1)
- [Identifying, Capturing, and Reusing Tacit Knowledge with Generative AI (UIST 2024)](https://dl.acm.org/doi/10.1145/3746058.3758467)
- [Tacit Knowledge Elicitation for Shop-floor Workers with an Intelligent Assistant (CHI 2023)](https://dl.acm.org/doi/10.1145/3544549.3585755)
- [Unveiling the Unspoken: AI-Enabled Tacit Knowledge Co-Evolution (MDPI)](https://www.mdpi.com/2673-9585/6/1/1)

---

## Synthesis: A Minimal Viable Environmental Awareness Stack

If Wizard were to implement the highest-signal, lowest-cost subset of the above, it would look like this:

| Signal | What it reveals | Source |
|---|---|---|
| Active git branch name | Current task frame | git CLI passively |
| Files open in editor | Current mental model | LSP / editor plugin |
| Time since last commit | Flow depth or stuckness | git log |
| Recent test pass/fail | Confidence level | test runner hooks |
| Session gap duration | Interruption vs. continuation | session timestamps |
| Edit velocity on a single file | Focus intensity | editor plugin |

None of these require biometrics, wearables, or surveillance. They are all observable from signals that already exist in the engineering environment. The question is not whether to capture them — it is what to do with them once captured.

The research suggests three things to do:
1. **Anchor notes to context signatures** so they surface when the context recurs (Ideas 1, 2)
2. **Infer task state passively** to protect flow and support resumption (Ideas 3, 5, 8)
3. **Ask targeted questions** only when behavioural signals suggest tacit knowledge worth capturing (Idea 9)

The goal is not a surveillance system. It is a cognitive prosthetic that reads the shape of the engineer's environment and uses that shape to be more useful — exactly as a good human pair programmer would, and exactly as Mark Weiser imagined computing would eventually become.
