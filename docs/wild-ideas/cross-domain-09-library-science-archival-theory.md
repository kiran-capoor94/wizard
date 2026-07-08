# Library Science, Archival Theory, and Information Architecture: What a Century of Hard-Won Knowledge Tells Us About AI Agent Memory

*Cross-domain research sweep — May 2026*

AI agent memory systems have been built almost entirely by ML engineers reading ML papers. But the problem they are trying to solve — "how do you store knowledge so it stays findable and useful over decades?" — was solved (partially, with enormous nuance) by library scientists, archivists, and information architects over the past 150 years. This document surveys what that field knows, where it agrees and disagrees with current AI memory design, and what Wizard is missing by not reading a single issue of *Archivaria* or *Library Quarterly*.

---

## Part I: The Canonical Frameworks

### 1. Ranganathan's Five Laws of Library Science (1931)

S.R. Ranganathan, a mathematician turned librarian at the University of Madras, published *The Five Laws of Library Science* in 1931. They are so durable they are being actively reinterpreted for AI systems in 2024–2025:

1. **Books are for use** — resources exist to be accessed, not collected for its own sake
2. **Every reader his book** — every person has the information they need; the system must match supply to demand
3. **Every book its reader** — every resource should reach the person who needs it; surfacing and recommendation are core responsibilities
4. **Save the time of the reader** — efficiency of retrieval is a primary design goal, not an afterthought
5. **The library is a growing organism** — the system must evolve; static collections die

Applied to Wizard directly:

- **Law 1** means notes exist to be retrieved and used, not just stored. Wizard currently has no "was this note ever retrieved after it was written?" signal — no usage loop.
- **Law 3** means Wizard should proactively surface notes to the agent without the agent having to ask for them. The `what_am_i_missing` tool is a step toward this. It should be more aggressive.
- **Law 4** means that reducing retrieval friction — not just retrieval accuracy — is a first-class metric. Vector search that returns 10 semantically-similar notes and buries the one you need in position 8 violates Law 4.
- **Law 5** is the most overlooked: Wizard's schema and taxonomy should be designed to evolve. Today's note types (`investigation`, `decision`, `docs`, `learnings`) are a fixed four-category flat taxonomy. Ranganathan would add a fifth law saying that taxonomy is a growing organism too.

**Sources:** [Wikipedia – Five Laws of Library Science](https://en.wikipedia.org/wiki/Five_laws_of_library_science) · [Emerald: AI and the Five Laws (2024)](https://www.emerald.com/lhtn/article-abstract/42/4/1/1264085/) · [Lucidea: Do the Five Laws Hold Up in a Digital World?](https://lucidea.com/blog/do-the-original-5-laws-of-library-science-hold-up-in-a-digital-world/)

---

### 2. FRBR: The Ontology of "What Is a Work?" (1998)

The International Federation of Library Associations (IFLA) published *Functional Requirements for Bibliographic Records* (FRBR) in 1998 as a conceptual entity-relationship model for bibliographic data. FRBR's core insight is that a "work" is not a single flat record — it exists at four levels of abstraction:

- **Work** — the abstract intellectual creation (the *idea* of Hamlet)
- **Expression** — a specific realization (the 1603 Quarto text vs. the 1623 Folio)
- **Manifestation** — a physical or digital embodiment (a specific printed edition)
- **Item** — a single copy held in a specific location

This four-level WEMI model was later consolidated into the **IFLA Library Reference Model (IFLA LRM)**, the current standard.

**What Wizard gets wrong by ignoring this:** Wizard's notes are flat Items. There is no concept of:
- A **Work** — "the decision to move from SQLite to Postgres" that exists across multiple sessions, decision notes, and task log entries
- An **Expression** — different articulations of the same insight at different levels of detail (a quick scratch note vs. a synthesis)
- A **Manifestation** — the same decision encoded as a task note, a session synthesis, and a Notion page

When Wizard does synthesis, it is collapsing multiple Expressions of the same Work into a single Item. The intellectual structure that made those notes related is discarded. Two months later, the agent has no way to know that the synthesis and the original notes are about the same Work.

An FRBR-aware Wizard would have a `work_id` on notes — a stable identifier that groups all notes/syntheses/tasks that are expressions of the same underlying intellectual object. This is distinct from a task ID. The task is an administrative grouping; the work is a conceptual grouping.

**Sources:** [Wikipedia – FRBR](https://en.wikipedia.org/wiki/Functional_Requirements_for_Bibliographic_Records) · [OCLC FRBR Research](https://www.oclc.org/research/activities/frbr.html) · [IFLA LRM](https://www.ifla.org/g/cataloguing/ifla-s-bibliographic-conceptual-models/) · [LOC FRBR PDF](https://www.loc.gov/cds/downloads/FRBR.PDF)

---

### 3. Dublin Core: The 15-Element Minimum Viable Metadata Standard (1995)

The Dublin Core Metadata Initiative emerged from a 1995 workshop in Dublin, Ohio, bringing together librarians, archivists, and early web engineers to define a minimal interoperable metadata standard for any knowledge object. The 15 core elements are:

`Creator · Contributor · Publisher · Title · Date · Language · Format · Subject · Description · Identifier · Relation · Source · Type · Coverage · Rights`

What makes Dublin Core significant is not the specific elements — it's the design philosophy behind them:
1. Every knowledge object has a **Relation** to other objects, and this is a first-class metadata field
2. Every object has a **Source** — where it came from, what it was derived from
3. **Coverage** (temporal and spatial scope) is a required metadata category, not an afterthought
4. **Rights** is core metadata — who owns this, can it be shared?

**What Wizard is missing from this list:**
- `Relation` — Wizard notes have no formal link to other notes except through shared task IDs. A note saying "I reconsidered the decision in note X" has no machine-readable link to note X.
- `Source` — when an agent creates a note during a task, what context window or transcript chunk was the source? This is gone.
- `Coverage` — what time period, codebase state, or project phase does this note's advice apply to? Without this, a note from 2024 about "don't use Alembic for schema migrations in this project" looks just as current as a note from today.

The Dublin Core recommendation to use persistent URIs as identifiers — specifically, to use HTTP URIs rather than internal integers — is directly relevant to Wizard's note identity model. A note ID of `7` is not a persistent identifier. A note ID of `wizard://kiran.capoor/notes/2026/session-42/inv-003` is.

**Sources:** [DCMI Metadata Basics](https://www.dublincore.org/resources/metadata-basics/) · [DCMI Metadata Terms](https://www.dublincore.org/specifications/dublin-core/dcmi-terms/) · [Practical Application of Dublin Core](https://asistdl.onlinelibrary.wiley.com/doi/full/10.1002/bul2.2017.1720430211)

---

### 4. Ranganathan's Colon Classification and Faceted Taxonomy (1933)

Ranganathan's second major contribution — the **Colon Classification** system (1933) — introduced **faceted classification** as an alternative to hierarchical taxonomy. His PMEST formula defines five fundamental facets for any subject:

- **P**ersonality — the most specific focal entity
- **M**atter — materials, properties, or substances involved
- **E**nergy — processes, operations, activities
- **S**pace — geographic or logical location
- **T**ime — dates, phases, periods

The colon between facets (hence "Colon Classification") indicates that any complex subject is a *combination* of these dimensions. A book about "the mechanical treatment of cotton in Gujarat in the nineteenth century" is: Cotton (P) : Mechanics (E) : Gujarat (S) : 19th century (T).

**What hierarchical taxonomies get wrong (and what Wizard does):** Wizard's current note type taxonomy (`investigation`, `decision`, `docs`, `learnings`) is a flat, single-axis categorization. A note can only be *one type*. But in practice, a note about "why we chose SQLite over Postgres for the synthesis queue" is simultaneously:
- A **decision** (it records a choice)
- An **investigation** (it documents findings)
- Scoped to a **time** (before the synthesis architecture was built)
- Scoped to a **component** (the synthesis service)
- Created with a particular **context** (a performance debugging session)

Faceted classification would let Wizard tag notes across all these dimensions simultaneously and retrieve them by any combination of facets: "show me all decisions about the database layer from before v2.0." That query is currently impossible.

**Sources:** [Wikipedia – Faceted Classification](https://en.wikipedia.org/wiki/Faceted_classification) · [Britannica – Colon Classification](https://www.britannica.com/science/Colon-Classification) · [Berkeley Pressbooks – Faceted Classification](https://berkeley.pressbooks.pub/tdo4p/chapter/faceted-classification/)

---

## Part II: Archival Theory

### 5. The Provenance Principle and Respect des Fonds (1841/1881)

Two of the oldest and most durable principles in archival science are **provenance** and **respect des fonds** (French: "respect for the collection"). Formally established by the French National Archives in 1841 and the Prussian State Archives in 1881, these principles hold that:

- **Provenance**: Records must be kept in relation to their creator and the activity that generated them. A letter from Napoleon's war ministry belongs with other war ministry records, not with other letters about the same battle.
- **Respect des fonds**: The integrity of a collection (fonds) must be preserved. You do not scatter documents from one creator into topical bins.
- **Original order**: Records should be maintained in the order their creator established — not reorganized by the archivist for their own convenience.

These principles exist because **meaning lives in context**. A document separated from its creator's other documents loses the relational meaning that makes it evidence of anything.

**What this means for Wizard:** Every note Wizard stores was created in a specific context: a session, a task, a mental state, a codebase state. The note's meaning is partially constituted by that context. When Wizard discards `transcript_raw` after synthesis (the current behavior), it is violating provenance — it is destroying the context of creation in the interest of storage efficiency.

The archival answer to "but we can't keep everything" is not "throw away the context" — it is to keep a *finding aid* (see section 7 below) that describes what the context was, even after the raw material is discarded. The key archival question is: can a future agent reconstruct *why* this note was written from the metadata alone? Currently, no.

**Sources:** [Wikipedia – Respect des fonds](https://en.wikipedia.org/wiki/Respect_des_fonds) · [Wikipedia – Original order](https://en.wikipedia.org/wiki/Original_order) · [Backlog Archivists – Provenance and Original Order](https://www.backlog-archivists.com/blog/provenance-and-original-order) · [Archive Journal – Disrespect des Fonds: Rethinking Born-Digital Archives](https://www.archivejournal.net/essays/disrespect-des-fonds-rethinking-arrangement-and-description-in-born-digital-archives/)

---

### 6. Archival Appraisal Theory: The Systematic Science of What to Keep

Archivists have developed a rigorous theory of **appraisal** — the principled process of deciding which records to preserve and which to destroy. This is the exact problem Wizard faces at scale: as sessions accumulate, not every note, synthesis, or session log is worth keeping forever.

**T.R. Schellenberg's dual-value theory (1956)** divided records into:
- **Primary value** — the record's value to its creator for administrative, fiscal, or operational use
- **Secondary value** — the lasting value after it's no longer in current use, subdivided into:
  - *Evidential value*: what the record tells us about the organization/person who created it
  - *Informational value*: what the record tells us about the subjects it documents

For Wizard: a note written during a debugging session has high *primary value* (immediate operational use) and variable *secondary value*. Schellenberg would ask: six months later, does this note tell us something evidential about how Kiran debugs (a pattern worth keeping) or something informational about a bug that no longer exists in the codebase (low secondary value, eligible for pruning)?

**Terry Cook's macro-appraisal (1992)** shifted the question from content to function. Rather than appraising records by what they contain, macro-appraisal asks *why were they created?* and *what function of the creator do they document?* Cook argued that records documenting the exercise of power and decision-making have higher archival value than records documenting routine operations, even if the routine records contain more data.

Applied to Wizard: decision notes (`type=decision`) have higher archival value than investigation notes (`type=investigation`) because they document the exercise of judgment. Investigation notes are often intermediate work products. This is an appraisal argument for differential retention schedules — not everything decays at the same rate.

**Sources:** [Wikipedia – Archival Appraisal](https://en.wikipedia.org/wiki/Archival_appraisal) · [Wikipedia – Terry Cook](https://en.wikipedia.org/wiki/Terry_Cook_(archivist)) · [Cook: Macro-appraisal and Functional Analysis (Journal of the Society of Archivists)](https://www.tandfonline.com/doi/abs/10.1080/0037981042000199106) · [Library Archives Canada Macro-Appraisal Methodology](https://www.bac-lac.gc.ca/eng/services/government-information-resources/disposition/Documents/MacroappraisalPartA.pdf) · [ACM CSCW: Archival Appraisal as Framework for Data Preservation](https://dl.acm.org/doi/10.1145/3415233)

---

### 7. The Archival Bond and Finding Aids (EAD)

The **archival bond** is the relationship that each record has with other records produced as part of the same transaction or activity. It is not context (which exists independently of the record) — it is an intrinsic part of the record itself. A record without its archival bonds is not a full record; it's an orphan document. Luciana Duranti, one of the foremost archival theorists, writes that the archival bond "is not to be confused with context" — it is the network of relationships that constitutes a record as *evidence* rather than mere data.

**Finding aids and EAD** are the practical infrastructure for navigating large archival collections without accessing every record. The **Encoded Archival Description** (EAD) XML standard, developed collaboratively by the Society of American Archivists and first published in 1998, provides a 146-element machine-readable schema for describing entire collections at multiple levels simultaneously — the collection, the series, the subseries, the folder, the item — without describing every item individually.

The key design insight: **a collection can be navigable without every item being fully described**. EAD allows an archivist to say "Series 3: Correspondence, 1943–1961, 4 linear feet, letters to and from State Department officials regarding postwar reconstruction" without describing each letter. Users can navigate to the right part of the collection and then look at individual items.

**For Wizard:** the equivalent of a finding aid is currently missing entirely. There is no document that says "Sessions 1-42 cover the initial Wizard architecture; Sessions 43-87 cover the synthesis system build; the key decision notes are X, Y, Z; the following notes are superseded." A finding aid would let the agent navigate to the right memory *region* before executing a vector search, rather than searching across all memory indiscriminately.

**Sources:** [Wikipedia – Archival Bond](https://en.wikipedia.org/wiki/Archival_bond) · [LOC – EAD Official Site](https://www.loc.gov/ead/) · [Wikipedia – EAD](https://en.wikipedia.org/wiki/Encoded_Archival_Description) · [SAA – EAD](https://www2.archivists.org/groups/technical-subcommittee-on-encoded-archival-standards-ts-eas/encoded-archival-description-ead) · [De Gruyter: From the Archival Bond to the Informational Bond (2023)](https://www.degruyterbrill.com/document/doi/10.1515/pdtc-2023-0004/html)

---

### 8. OAIS: The Reference Model for Long-Term Digital Preservation (1997/2025)

The **Open Archival Information System** (OAIS), now ISO 14721:2025 (third edition released December 2024), is the canonical reference model for institutions responsible for preserving digital content over decades. It was originally developed by NASA's Consultative Committee for Space Data Systems for preserving space mission data, but has become the dominant model across libraries, national archives, and research institutions worldwide.

OAIS defines three information package types that are directly analogous to problems Wizard has:

- **Submission Information Package (SIP)** — what the creator submits: raw transcripts, unstructured notes, tool call logs
- **Archival Information Package (AIP)** — the preserved form: structured, normalized, with full preservation metadata
- **Dissemination Information Package (DIP)** — what is returned to a consumer: a cleaned, context-enriched response

The gap between SIP and AIP is exactly Wizard's synthesis step — turning raw transcripts into structured notes. But OAIS mandates that the AIP contain not just the content but also **representation information** (how to interpret the content in the future), **preservation description information** (what was done to it, why, when), and **packaging information** (what holds it all together).

OAIS also defines the concept of the **Designated Community** — the anticipated future audience for the preserved material. This forces the archivist to ask: *who is this for, in 10 years?* The answer shapes every preservation decision. Wizard has no concept of a Designated Community. Notes are written for "the agent now" without asking "will this note make sense to an AI agent in 2028 with a different context window, different codebase state, and no memory of this session?"

**Sources:** [Wikipedia – OAIS](https://en.wikipedia.org/wiki/Open_Archival_Information_System) · [ISO 14721:2025](https://www.iso.org/standard/87471.html) · [OCLC OAIS Introductory Guide (2nd ed.)](https://www.oclc.org/research/publications/2014/open-archival-info-system-oais-ref-model-intro-guide-second-ed.html) · [Preservica: OAIS v3 Updates](https://preservica.com/resources/blogs-and-news/what-you-need-to-know-about-the-most-recent-oais-revision)

---

## Part III: Information Architecture

### 9. Peter Morville's Findability and the Honeycomb Model

**Peter Morville** co-authored *Information Architecture for the World Wide Web* (O'Reilly, 1998, with Louis Rosenfeld) — the definitive text that established information architecture as a discipline — and followed it with *Ambient Findability* (O'Reilly, 2005). His contribution is framing findability not as a search problem but as a *system design* problem.

Morville's **User Experience Honeycomb** defines seven qualities any useful information system must have: useful, usable, desirable, findable, accessible, credible, and valuable. Findability is the specific quality of being "locatable and navigable" — and Morville argues it requires three things working together: **good content**, **good metadata**, and **good navigation structure**. Improve any one and you hit the ceiling imposed by the other two.

His concept of **ambient findability** — that in a sufficiently instrumented environment, any information should be findable from any context — points directly at what AI agents need: a memory system where the agent doesn't need to know what to search for in order to find what it needs. The information comes to the agent based on ambient context signals, not explicit queries.

**Morville's information architecture** distinguishes between:
- **Organization systems** — how content is categorized
- **Labeling systems** — how content is named and described
- **Navigation systems** — how users move through the content space
- **Search systems** — how users query the content

Wizard has a search system (vector + FTS). It has a minimal organization system (note types, task IDs). It has almost no labeling system (notes are labeled by the agent's free text). It has no navigation system — there is no way to *browse* Wizard's memory, only to query it.

**Sources:** [Wikipedia – Peter Morville](https://en.wikipedia.org/wiki/Peter_Morville) · [O'Reilly – Ambient Findability](https://www.oreilly.com/library/view/ambient-findability/0596007655/) · [Boxes and Arrows – Ambient Findability Interview](https://boxesandarrows.com/ambient-findability-talking-with-peter-morville/)

---

### 10. Richard Saul Wurman: Information Anxiety and the LATCH Principles (1989)

**Richard Saul Wurman** coined the term "information architecture" in a 1976 American Institute of Architecture conference talk and published *Information Anxiety* in 1989 — diagnosing what happens when data volume exceeds a person's (or system's) ability to process it into meaning. His core distinction: **data is not information**. Raw data becomes information only when it is given form and applied.

Wurman's **LATCH framework** holds that all information can be organized in exactly five ways:
- **L**ocation — spatial proximity
- **A**lphabet — alphabetical order (useful only for reference, not for understanding)
- **T**ime — chronological sequence
- **C**ategory — group membership
- **H**ierarchy — ranking by magnitude or importance

This is a design claim: any organizational scheme that doesn't reduce to one of these five is confused. Wizard currently uses Time (sessions are chronological) and Category (note types). It does not use Location (what part of the codebase does this note concern?), Hierarchy (which notes are most critical vs. peripheral?), or a principled use of Alphabet at all.

Wurman would argue that Wizard's primary organization — chronological sessions with flat note types — is optimized for *recording* (writing) not for *understanding* (reading). The agent who wrote the note and the agent who retrieves it six months later have completely different needs. The writing interface is optimized for capture; the reading interface is not optimized for understanding.

**Sources:** [Wurman – Information Anxiety: Towards Understanding](https://www.wurman.com/publishedarticles/2017/5/5/information-anxiety-towards-understanding) · [Scenario Journal – Information Anxiety](https://scenariojournal.com/article/richard-wurman/) · [Medium – Information Architecture & Wurman](https://erinkmalone.medium.com/information-age-information-architecture-richard-saul-wurman-intro-lecture-12-e7e9ee86625f)

---

### 11. Jesse James Garrett and the Five Planes of Information Structure

**Jesse James Garrett** published his foundational diagram *The Elements of User Experience* in 2000 (book 2002), establishing a five-layer model for understanding any information system from the bottom up:

1. **Strategy** — user needs and site objectives (what is this for, who is it for?)
2. **Scope** — functional specifications and content requirements (what content exists?)
3. **Structure** — interaction design and information architecture (how is content organized?)
4. **Skeleton** — interface design, navigation design, information design (how is structure expressed?)
5. **Surface** — visual design (what does it look like?)

Garrett's model is relevant because it exposes the layers at which Wizard has made design decisions and the layers where it has not. Wizard has strong opinions about Surface (the MCP tool interface) and Skeleton (the `save_note`, `search`, `session_start` API). It has almost no deliberate design at the Strategy layer: *what does an AI coding agent actually need from its memory six months from now?* and *what does the human engineer need when reviewing what their agent did and decided?*

The Strategy plane question is the hardest: is Wizard's designated community the **current agent** (optimized for retrieval during an active session), the **future agent** (optimized for historical context), the **human engineer** (optimized for audit and review), or some weighted combination? Garrett would say this question must be answered before any lower-plane design can be correct.

**Sources:** [Wikipedia – Jesse James Garrett](https://en.wikipedia.org/wiki/Jesse_James_Garrett) · [JJG.net – Elements of User Experience](http://www.jjg.net/elements/) · [O'Reilly – Elements of User Experience](https://www.oreilly.com/library/view/the-elements-of/9780321688651/)

---

### 12. Information Foraging Theory: Pirolli and Card on Information Scent (1999)

**Peter Pirolli** and **Stuart Card** at XEROX PARC published *Information Foraging* in 1999, applying optimal foraging theory (how animals hunt for food) to how humans hunt for information. The framework introduces two key concepts:

**Information scent** is the imperfect signal that a source contains what you need, perceived through proximal cues — titles, links, summaries, icons. Users follow the scent gradient: they move toward sources where the scent gets stronger and abandon sources where it plateaus or weakens. A memory system with poor information scent — where the proximal cues on notes do not reliably indicate whether the full note is relevant — will cause agents to over-retrieve (expensive) or under-retrieve (wrong answers).

**Information patches** are clusters of related information. Like animals moving between food patches, agents move between information patches. The decision to leave a patch (stop searching within a context) is governed by the **marginal value theorem**: leave when the expected rate of gain from the current patch falls below the average rate across all patches.

**What AI agent memory systems get wrong here:** they optimize for recall (does the right note appear in results?) without optimizing for scent (does the agent *know* the right note appeared in results?). Vector similarity is a weak scent signal. A note titled "investigation: considered three database options, settled on SQLite" has high scent for a future query about database decisions. A note titled "session note 42 findings" has almost no scent. Wizard's current free-text note titles are not a controlled labeling system — they are whatever the agent happened to write, which varies enormously in scent quality.

Pirolli and Card's framework also suggests that **dense patches beat sparse patches** for navigation: if related notes are co-located (in a folder, in a session, in a topic cluster), the agent can forage within the patch. If related notes are scattered across 180 sessions, the foraging cost is prohibitive regardless of vector search quality.

**Sources:** [NN/g – Information Foraging](https://www.nngroup.com/articles/information-foraging/) · [Peter Pirolli – Information Foraging Theory](https://www.peterpirolli.com/Professional/About_Me_files/IFT%20Ch%201.pdf) · [Wikipedia – Information Foraging](https://en.wikipedia.org/wiki/Information_foraging)

---

### 13. Brenda Dervin's Sense-Making Theory: The Gap-Bridging Model (1983)

**Brenda Dervin** at Ohio State University developed **Sense-Making Methodology** in the 1980s as a framework for understanding how people actually use information. The core metaphor: a person moves through life until they hit a **gap** — a situation where their current understanding does not match their experience. They then seek information to **bridge** the gap and continue moving forward.

This is directly analogous to how an agent uses Wizard: the agent hits a gap (unclear how to proceed, doesn't remember a past decision, needs historical context) and queries Wizard to bridge it. Dervin's research shows that people rarely ask for what they actually need — they ask for what they think is available, or they ask the wrong question because they don't yet understand the structure of their gap.

The **reference interview** (see below) is the librarian's practical response to this problem. But for AI agents, the implication is: *a memory system should be designed around the structure of common gaps, not around the structure of common queries.* Wizard's search is query-optimized. A gap-optimized design would ask: what are the 10 most common types of uncertainty an agent faces during a coding session, and how should the memory system be structured to bridge each of them efficiently?

Dervin's framework also surfaces a concept AI memory consistently ignores: **situatedness**. Information has meaning only in relation to the situation of the person/agent seeking it. A note is not useful in the abstract — it is useful *to this agent, in this context, at this moment, facing this gap*. Wizard has no model of the agent's current situation when it retrieves notes. It treats all queries as context-free.

**Sources:** [ResearchGate – Dervin's Sense-Making Theory](https://www.researchgate.net/publication/284311730_Dervin_s_Sense-Making_Theory) · [JASIST – Information Use as Gap-Bridging (2006)](https://onlinelibrary.wiley.com/doi/abs/10.1002/asi.20400) · [EPIC – Sensemaking Methodology](https://www.epicpeople.org/sensemaking-methodology/)

---

### 14. The Reference Interview: Structured Elicitation of True Information Need

The **reference interview** is the librarian's 70-year-old technique for the following problem: patrons rarely ask for what they actually need. They ask for what they think the library can provide, or they ask for a solution to a symptom rather than the root problem. A patron asking for "books about World War II" might need "sources for a paper arguing that the Molotov-Ribbentrop Pact was determinative" — an entirely different retrieval task.

The reference interview uses active listening, open-ended questions, clarification, and paraphrasing to identify the patron's **true information need** (the gap they need to bridge) as distinct from their **stated query** (what they asked for). Key techniques include:
- Open questions to establish context ("What are you working on?")
- Clarifying questions to narrow scope ("Are you looking for background or primary sources?")
- Neutral probes that encourage elaboration without leading
- Verification at the end ("Does this look like what you were after?")

**For Wizard's `what_am_i_missing` tool and session context:** the current implementation asks the agent to describe what it's working on and returns what might be missing. This is a one-shot query with no structured elicitation. A reference-interview-informed design would model the session context across multiple turns before making retrieval decisions — building an increasingly precise picture of the agent's gap before surfacing memory. The agent's `session_start` call and subsequent `task_start` calls are the raw material for this; they are currently used only for organizational tagging, not for building a mental model of the agent's information need.

**Sources:** [Wikipedia – Reference Interview](https://en.wikipedia.org/wiki/Reference_interview) · [LISE Network – Reference Interview](https://www.lisedunetwork.com/understanding-the-reference-interview-purpose-process-and-importance-in-modern-libraries/) · [Data Intelligence Platform – The Librarian's Reference Interview for Data Teams](https://dataintelligenceplatform.substack.com/p/the-librarians-reference-interview)

---

### 15. William Jones: Personal Information Management and the Re-Finding Problem (2007)

**William Jones** at the University of Washington published *Keeping Found Things Found: The Study and Practice of Personal Information Management* (Elsevier, 2007) — the first book-length treatment of how individuals manage their personal information collections. His central observation: **re-finding is as hard as finding**. People expend enormous effort re-locating information they have already encountered and "saved" somewhere.

Jones identifies five PIM activities:
1. **Keeping** — deciding what to save and where
2. **Finding/re-finding** — locating information when needed
3. **Organizing** — structuring kept information
4. **Maintaining** — keeping the collection current and useful
5. **Meta-level activities** — deciding how to manage the system itself

The finding/re-finding distinction is critical for Wizard: the agent who *writes* a note is performing a **keeping** activity. The agent who retrieves it six months later is performing a **re-finding** activity. These two activities have fundamentally different requirements. Keeping is optimized for low friction at capture time; re-finding requires that the kept item have enough context attached that a future agent — with no memory of the keeping event — can identify it as relevant.

Jones' research consistently finds that **people over-save and under-describe** — they keep more than they need and write descriptions that make sense at capture time but become opaque six months later. Wizard's current architecture has exactly this failure mode: notes are captured with whatever context the agent happened to provide, with no systematic enforcement of description quality.

**Sources:** [Elsevier – Keeping Found Things Found](https://shop.elsevier.com/books/keeping-found-things-found-the-study-and-practice-of-personal-information-management/jones/978-0-12-370866-3) · [ACM Digital Library](https://dl.acm.org/doi/10.5555/2155696) · [Springer – The Future of Personal Information Management](https://link.springer.com/book/10.1007/978-3-031-02278-4)

---

## Part IV: What the Field Is Building Now (2025–2026)

### 16. Content Authenticity and Provenance for AI-Generated Content

The library, archives, and museum (LAM) community published a joint white paper in February 2026 — *Content Authenticity and Provenance in the Age of Artificial Intelligence: A Call to Action for the LAMs Community* — arguing that AI-generated and AI-modified content requires the same provenance infrastructure that libraries have applied to physical records for 150 years.

The emerging technical standard is **C2PA (Coalition for Content Provenance and Authenticity)**, specification v2.2 released May 2025, founded by Adobe, BBC, Microsoft, and others. C2PA Manifests record: who created the content, when, what tools were used, whether AI was involved in creation or modification, and a cryptographically-verified audit trail of every meaningful edit.

The Library of Congress's *The Signal* blog published coverage of this as a call-to-action in April 2026, arguing that the fundamental archival question — *can we trust this record, and can we verify its chain of custody?* — now applies to every AI-generated note, synthesis, or decision record.

**For Wizard:** every note is created by an AI agent, potentially revised by another AI agent during synthesis, and potentially summarized again later. There is no provenance chain on the note record itself. Who synthesized this? What model? What context window did it have access to? What was the synthesis prompt? These are preservation metadata questions. Without them, a note synthesized by Claude Sonnet 3.7 with a specific context window has no way to be distinguished from a note synthesized by a future model with different capabilities and different hallucination patterns.

**Sources:** [LOC Signal – Content Authenticity and Provenance (April 2026)](https://blogs.loc.gov/thesignal/2026/04/content-authenticity-and-provenance-in-the-age-of-artificial-intelligence-a-call-to-action-for-the-libraries-archives-and-museums-community/) · [C2PA.org](https://c2pa.org/) · [Content Authenticity Initiative](https://contentauthenticity.org/)

---

### 17. BIBFRAME and the Linked Data Transition in Libraries (2024–2026)

The Library of Congress began full production cataloging in **BIBFRAME** in 2024, transitioning away from the 50-year-old MARC format. BIBFRAME (Bibliographic Framework) is an RDF/linked data model that replaces flat MARC records with a graph of interlinked entities — Works, Instances, Items, Agents, Subjects, Events — where every entity is identified by a persistent HTTP URI and relationships between entities are explicit, machine-traversable links.

By May 2025, 300+ catalogers across 400+ languages were producing BIBFRAME records in production. The broader significance: the library world's canonical knowledge representation format is now a knowledge graph with explicit entity relationships, not a flat record with implicit string matches.

**For Wizard:** Wizard's notes are flat records with string-typed foreign keys (task IDs, session IDs). The BIBFRAME transition is evidence that the field has concluded that flat records with string relationships are fundamentally inadequate for knowledge that needs to remain useful over decades. An entity-graph model — where notes are linked to the specific Decisions they instantiate, to the Codebase entities they concern, to the Sessions that generated them, and to other Notes they contradict or supersede — is where the library field has arrived after 50 years of trying flat records.

**Sources:** [ExLibris – From MARC to BIBFRAME](https://exlibrisgroup.com/blog/from-marc-to-bibframe-what-linked-data-means-for-libraries-in-practice/) · [Wikipedia – BIBFRAME](https://en.wikipedia.org/wiki/BIBFRAME) · [My Librarianship – The Linked Data Revolution (March 2025)](https://mylibrarianship.wordpress.com/2025/03/13/a-new-chapter-for-library-data-the-linked-data-revolution/) · [LOC – BIBFRAME](https://www.loc.gov/aba/pcc/documents/bibframe-pcc.html)

---

### 18. Knowledge Obsolescence: The Half-Life of Information

Library and information science has systematically studied **knowledge obsolescence** — the process by which information loses relevance, utility, or accuracy over time. The **cited half-life** of a discipline measures how quickly older work stops being cited: for Library and Information Science itself, it's 8 years. For computer science, it's considerably shorter — on the order of 4–5 years in fast-moving subfields.

The practical implication for Wizard: **notes have a half-life**, and it is not infinite. A note from 2024 advising "use Celery for background task processing" may be actively harmful by 2027 if the architecture has changed. Notes are not wine — they do not improve with age. They decay in three ways:
1. **Technical obsolescence** — the codebase, libraries, or patterns described no longer exist
2. **Decisional obsolescence** — the decision documented has been revisited and reversed
3. **Contextual obsolescence** — the context that made the note meaningful (the team, the project phase, the constraints) no longer exists

Libraries handle this with **weeding policies** — systematic removal of outdated material — and with temporal metadata that makes age visible. Wizard currently surfaces a 2-year-old note with the same visual weight as a note from yesterday. Age is queryable but not surfaced in retrieval ranking.

**Sources:** [LIS Academy – Obsolescence of Scientific Literature](https://lis.academy/informetrics-scientometrics/obsolescence-scientific-literature-concepts-patterns/) · [Wikipedia – Temporal Information Retrieval](https://en.wikipedia.org/wiki/Temporal_information_retrieval) · [Springer – Modeling Obsolescence of Research Literature (2022)](https://link.springer.com/article/10.1007/s11192-022-04359-w)

---

## Part V: The Five Principles Library Science Would Add to Wizard's Design

These are not incremental feature suggestions. They are structural design principles that Wizard's engineers never considered because they were not reading the right literature.

---

### Principle 1: Provenance Is Not Optional — The Context of Creation Is Part of the Record

**From:** Archival theory — respect des fonds, archival bond, OAIS representation information.

**The principle:** A note without its creation context is an orphan document. The model that synthesized it, the session that produced it, the task state at the time of writing, the codebase commit — these are not optional metadata fields to be discarded for storage efficiency. They are the **context of creation** that makes the note evidence of something rather than mere assertion.

**Specific implication for Wizard:** When `transcript_raw` is cleared after synthesis (current behavior), the synthesis output should include an immutable provenance block: synthesis model name + version, synthesis prompt template version, session ID, task IDs in scope, timestamp, and a hash of the raw transcript (even if the transcript itself is deleted). This allows a future agent to know *how* a note came to exist, which is necessary for deciding how much to trust it.

---

### Principle 2: Notes Have a Half-Life — Temporal Decay Must Be Modeled, Not Ignored

**From:** Schellenberg appraisal theory, LIS obsolescence research, OAIS Preservation Planning functional entity.

**The principle:** Information loses value at different rates depending on its type, scope, and the rate of change of the domain it describes. A system that treats all notes as equally current is a system that actively misleads the agent over time.

**Specific implication for Wizard:** Every note should have a `relevance_scope` field with a machine-readable temporal qualifier: `session` (relevant only to this session), `project-phase` (relevant until the architecture changes), `persistent` (decision rationale, unlikely to become obsolete), or `technical` (depends on current codebase state, high obsolescence risk). Retrieval ranking should penalize notes whose `relevance_scope` has likely expired. A `technical` note from 18 months ago should rank below a `technical` note from last week unless there is explicit evidence the old note is still applicable.

---

### Principle 3: Faceted, Not Flat — Every Note Has Multiple Independent Classification Axes

**From:** Ranganathan's Colon Classification, faceted classification theory.

**The principle:** A single-axis categorical taxonomy (`type: investigation | decision | docs | learnings`) cannot represent the multidimensional reality of engineering knowledge. Every note simultaneously belongs to multiple classification facets, and retrieval quality degrades severely when only one axis is modeled.

**Specific implication for Wizard:** Add at minimum three independent classification axes alongside the existing `type`:
1. **Component scope** — which part of the system does this concern? (synthesis, storage, MCP interface, jira-integration, etc.) — derived from file paths mentioned
2. **Decision maturity** — exploratory / decided / superseded / reversed
3. **Confidence level** — observed / inferred / assumed / verified

The combination of `type=decision`, `component=synthesis`, `maturity=superseded` is a precise retrieval target. `type=decision` alone is not.

---

### Principle 4: The Memory System Needs a Finding Aid — Navigable Structure Independent of Search

**From:** EAD finding aids, Morville's navigation systems, Ranganathan's Fifth Law (the library is a growing organism).

**The principle:** A query interface is not a navigation interface. Users (and agents) need to be able to *browse* a memory collection at multiple levels of granularity — from "what major decisions were made about the synthesis architecture?" down to "what were the alternatives considered?" — without knowing the exact query terms in advance. This requires a hierarchically-structured description of the collection that is maintained as the collection grows.

**Specific implication for Wizard:** Generate and maintain a **memory index** — a structured document (or database view) that describes the memory collection at the project-phase level, the architecture-domain level, and the key-decision level. Something like: "Phase 2 (sessions 43–87): Synthesis System. Key decisions: [D-001 SQLite for synthesis queue, D-002 transcript_raw cleared after synthesis, D-003 ...]. Active investigation threads: [...]. Superseded decisions: [...]." This index is the finding aid. The agent can retrieve the finding aid first, then execute targeted searches within the right region of memory.

---

### Principle 5: Write for the Future Agent, Not the Current Agent — The Designated Community Problem

**From:** OAIS Designated Community concept, William Jones' PIM re-finding research, Brenda Dervin's situatedness.

**The principle:** The agent who writes a note and the agent who retrieves it are, for practical purposes, different agents with no shared context. Notes written for the current agent's immediate convenience are systematically under-described for the future agent's re-finding needs. The "Designated Community" for Wizard's memory is not the current session — it is the agent who will encounter this note in an unknown future context and must decide, based only on the note's text and metadata, whether it is relevant to their current gap.

**Specific implication for Wizard:** The note-taking prompt and synthesis prompts should be redesigned around the question: *"If a competent engineer who has never seen this codebase reads this note in 18 months, will they be able to understand: (a) what context produced this note, (b) what was decided or discovered, (c) what would make this note no longer applicable?"* Notes that fail this test should be flagged for enhancement, not just accepted. The `mental_model` field in the current note-taking template is a step in this direction. It should be mandatory and structured, not optional and free-text.

---

## Appendix: Thinkers and Standards Reference

| Name | Contribution | Key Work |
|------|-------------|----------|
| S.R. Ranganathan (1892–1972) | Five Laws, Colon Classification, faceted taxonomy | *Five Laws of Library Science* (1931) |
| T.R. Schellenberg (1903–1970) | Primary/secondary value, appraisal theory | *Modern Archives: Principles and Techniques* (1956) |
| Terry Cook (1947–2014) | Macro-appraisal, functional analysis, archival silences | *Archivaria* journal, multiple essays 1992–2011 |
| Luciana Duranti | Archival bond, diplomatics, trustworthiness of records | *Diplomatics: New Uses for an Old Science* (1998) |
| Peter Morville | Findability, ambient findability, information architecture honeycomb | *Information Architecture for the WWW* (1998), *Ambient Findability* (2005) |
| Richard Saul Wurman | Information anxiety, LATCH organization principles | *Information Anxiety* (1989) |
| Jesse James Garrett | Elements of user experience, five planes model | *Elements of User Experience* (2002) |
| Peter Pirolli & Stuart Card | Information foraging, information scent theory | *Information Foraging* (PARC, 1999) |
| Brenda Dervin | Sense-making theory, gap-bridging model | Numerous journal articles, Ohio State 1983+ |
| William Jones | Personal information management, re-finding problem | *Keeping Found Things Found* (2007) |
| IFLA | FRBR, IFLA LRM bibliographic ontology | FRBR (1998), IFLA LRM (2017) |
| Dublin Core Metadata Initiative | 15-element universal metadata standard | DCMI Metadata Terms (1995–present) |
| SAA / LOC | EAD finding aid standard | EAD (1998), EAD3 (2015) |
| CCSDS / ISO | OAIS reference model for digital preservation | ISO 14721:2025 |
| C2PA | Content authenticity and provenance standard | C2PA Specification v2.2 (May 2025) |
| Library of Congress | BIBFRAME linked data cataloging standard | BIBFRAME (2012–present, production 2024) |
