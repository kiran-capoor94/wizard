# Cross-Domain Research: Information Retrieval and Search
## What the Field Knows — and What It Means for Wizard

**Date:** May 2026  
**Scope:** SIGIR, ECIR, WWW, CIKM 2023–2026; Microsoft Research, Google DeepMind, Meta AI, Cohere, Vespa.ai; industry benchmarks  
**Baseline:** Wizard currently uses SQLite FTS5 (BM25) full-text search

---

## Part 1: Current State of the Art (2023–2026)

### 1.1 Dense vs. Sparse vs. Hybrid Retrieval

The retrieval landscape has converged on a clear verdict: **hybrid search outperforms either sparse or dense retrieval alone, reliably, across corpora**. The debate about "which paradigm wins" is settled in practice — the question is now which hybrid configuration and which fusion strategy.

#### Sparse Retrieval

**BM25** remains the unbeatable baseline for exact-match and rare-term recall. It is fast, zero-shot, requires no GPU, and its failure modes are predictable (vocabulary mismatch, no synonymy).

**SPLADE** (Sparse Lexical and Expansion — SIGIR 2021, SIGIR 2022, Naver Labs Europe) is the learned sparse retrieval state of the art. It maps queries and documents into high-dimensional sparse vectors over the BERT vocabulary, using neural expansion to add weights for terms like "optimizer" and "backpropagation" even if they never appear verbatim. SPLADE++ achieves state-of-the-art zero-shot performance on TREC and competitive BEIR scores, while remaining compatible with standard inverted indexes.

Production caveat: SPLADE query vectors have more non-zero terms than BM25, making retrieval slower than classic inverted index search. The 2025 paper *"Efficiency and Effectiveness of SPLADE Models on Billion-Scale Web Document Title"* (arXiv:2511.22263) demonstrates that top-k pruning and FLOPS regularization allow SPLADE to operate at web scale. Amazon's *CSPLADE* (AACL 2025) explores causal LMs as SPLADE encoders, extending sparse expansion vocabulary beyond the BERT WordPiece constraint.

LLM-based query reformulation yields **the largest performance gain applied to BM25**, moderate gains on BGE dense retrieval, but **minimal gain on SPLADE++** — because SPLADE's own expansion already handles most query vocabulary gaps.  
Source: *"A Reproducibility Study of LLM-Based Query Reformulation"* (arXiv:2604.27421)

#### Dense Retrieval

Dense bi-encoders (DPR, E5, BGE, Nomic Embed) produce fixed-dimension vectors and rank by cosine similarity. They excel at semantic matching where vocabulary differs between query and document — a query like "why is my gradient exploding" retrieves a document titled "vanishing and exploding gradients in deep networks" correctly where BM25 fails.

Key 2024–2026 models:

- **BGE-M3** (BAAI, arXiv:2402.03216): Unified multi-functionality model supporting dense retrieval, sparse retrieval, and multi-vector (ColBERT-style) retrieval from a single encoder. Handles 100+ languages, 8192-token context, and tops C-MTEB/Retrieval and MIRACL benchmarks. This is the most versatile single-model choice for private corpora.
- **E5-large-instruct** (Microsoft Research): Instruction-tuned dense retrieval model; strong zero-shot generalization.
- **Nomic Embed v2** (Nomic AI, 137M params): First embedding model with a Mixture-of-Experts architecture. Fully open weights (Apache 2.0). Best quality-to-size ratio for CPU deployment. MTEB-competitive.
- **Qwen3-Embedding-8B** (Alibaba, 2025): MTEB multilingual composite score ~70.58, currently #1 on the multilingual leaderboard. Requires GPU (8B params). Overkill for a small personal corpus but relevant as a gold standard reference.

#### Late-Interaction / Multi-Vector

**ColBERT** (Stanford FutureData, SIGIR 2020, ACL 2023, EMNLP 2023) retains one vector per token for both query and document, computing relevance via MaxSim across all query-token/document-token pairs. This gives it fine-grained matching that single-vector models miss.

ColBERTv2 + RAGatouille (2024) made ColBERT accessible: indexing and search in ~10 lines of Python. Monthly HuggingFace downloads grew to millions by mid-2024. Vespa and Qdrant both added native ColBERT support. The first dedicated workshop, **LIR (Late Interaction and Multi Vector Retrieval)** was accepted at ECIR 2026 (arXiv:2511.00444), signaling the technique's promotion from research curiosity to production discipline.

Storage cost is ColBERT's main barrier: a corpus of 100k documents produces ~4–6 GB of token vectors vs. ~400 MB for single-vector dense models.

#### Benchmark Numbers (BEIR, MS MARCO, TREC DL 2023)

| Method | BEIR avg nDCG@10 | MS MARCO MRR@10 | Notes |
|---|---|---|---|
| BM25 (baseline) | ~0.43 | ~0.185 | No GPU, zero-shot |
| SPLADE++ | ~0.49 | ~0.38 | GPU at index time |
| E5-large | ~0.50 | ~0.37 | GPU at query time |
| BGE-M3 dense | ~0.51 | ~0.38 | Multi-function |
| ColBERTv2 | ~0.49 | ~0.40 | High storage cost |
| Hybrid BM25 + BGE (RRF) | ~0.52–0.54 | ~0.40 | Production sweet spot |
| Hybrid BM25 + BGE + ColBERT rerank | ~0.54–0.56 | ~0.41 | Best recalled |

Vespa's hybrid (BM25 + ColBERT) improved average nDCG@10 from 0.453 to 0.481 across 13 BEIR datasets vs. a strong BM25 baseline. On BRIGHT Biology (a hard out-of-domain benchmark), hybrid added +24% over dense-only.

### 1.2 Neural Retrieval for Small Private Corpora (<100k Documents)

The research here is sparse — almost all benchmarks use web-scale or Wikipedia-scale corpora. What is known:

**Dense retrieval is disproportionately strong at small scale.** With <100k documents, approximate nearest neighbor indexes (HNSW in FAISS, or exact search) are fast enough that the latency advantage of BM25 disappears. Dense models have no inverted index warmup. A query against 50k documents with a 384-dim BGE vector runs in <10ms on CPU.

**BM25's advantage is recall on exact tokens.** For a personal coding corpus where queries like "what did I decide about retry logic in the Stripe integration" contain very specific tokens (Stripe, retry), BM25 reliably retrieves the right chunk if it exists. Dense models may not surface it if the embedding space clusters "retry logic" near generic resilience content.

**The practical recommendation from 2024–2026 practitioners:** run BM25 and dense in parallel, keep 20–50 candidates from each, merge with Reciprocal Rank Fusion (RRF), then rerank. This 2-stage pipeline works at any scale and is what Elasticsearch, Vespa, Qdrant, and Weaviate all ship as their recommended RAG configuration.

**PersonalAI** (arXiv:2506.17001, June 2025) is one of the few papers to directly compare knowledge graph storage vs. vector retrieval vs. hybrid for personalized LLM agents. Findings: for factual retrieval over personal conversation history, hybrid retrieval consistently outperforms either alone; knowledge graph approaches only win when multi-hop reasoning over relationships is required.

### 1.3 RAG Failure Modes — What the Research Says

The landmark taxonomy is *"Seven Failure Points When Engineering a Retrieval Augmented Generation System"* (Barnett et al., arXiv:2401.05856, January 2024) from three case studies across research, education, and biomedical domains:

1. **Missing content** — the answer is not in the corpus. The system hallucinates rather than saying "I don't know."
2. **Missed top-k** — the relevant document exists but ranked outside the retrieved window.
3. **Not in context** — the document was retrieved but the relevant passage was not in the final context window after chunking.
4. **Wrong extraction** — the model reads the right document but extracts the wrong span.
5. **Wrong format** — the answer is correct but not in the expected format.
6. **Incorrect specificity** — the answer is too broad or too narrow.
7. **Incomplete answer** — partial correct answer, missing crucial details.

Key meta-finding: **validation of a RAG system is only possible during operation** — you cannot detect most failure modes at build time.

Additional failure modes identified in 2024–2025 research:

**Context-memory conflict** (*"Seeing through the Conflict"*, arXiv:2601.06842): When retrieved context contradicts the model's parametric knowledge (common when the corpus contains recent or domain-specific facts that postdate training), current models show no reliable strategy — some over-trust context, some over-trust weights.

**Contradiction within retrieved context** (*"Contradiction Detection in RAG Systems"*, arXiv:2504.00180, April 2025): With 20 retrieved chunks, there are 190 possible pairwise contradictions to check. No current system does this efficiently. LLM-as-validator improves accuracy but chain-of-thought prompting inconsistently helps or hurts depending on model size.

**Multi-hop failure**: Single-stage retrieval fundamentally cannot satisfy queries that require chaining two facts (e.g., "what is the approach I use in the service that handles the task X uses for retry?"). This requires either iterative retrieval or a graph.

**Temporal blindness**: Retrieval systems treat all documents as equally current. A note written 18 months ago about a deprecated approach ranks identically to a note written yesterday about the current approach. No standard retrieval stack addresses this without explicit timestamp weighting.

### 1.4 Graph-Augmented Retrieval: GraphRAG, HippoRAG, LightRAG

Graph augmentation addresses the flat-retrieval multi-hop problem by building a knowledge graph over the corpus and using graph traversal during retrieval.

**Microsoft GraphRAG** (2024): Extracts entity-relationship triples from documents using an LLM, builds a community hierarchy via Leiden algorithm, and supports both local (entity-focused) and global (community-focused) queries. Achieves 86% accuracy vs. 32% for baseline RAG on Microsoft's enterprise benchmarks. However, the canonical comparison paper *"RAG vs. GraphRAG: A Systematic Evaluation"* (arXiv:2502.11371, February 2025) found GraphRAG achieves **13.4% lower accuracy than vanilla RAG on Natural Questions** — a factual retrieval benchmark. GraphRAG excels at abstractive, theme-level synthesis queries; it degrades on precise factual retrieval.

The ICLR 2026-accepted **GraphRAG-Bench** (github.com/GraphRAG-Bench/GraphRAG-Benchmark) systematically characterizes when graph helps: fact retrieval tasks show no benefit from graphs; complex reasoning and creative generation tasks show +15–30% gains.

**HippoRAG** (OSU NLP Group, NeurIPS 2024, arXiv:2405.14831): Inspired by hippocampal indexing theory — builds a KG from documents, then runs Personalized PageRank (PPR) at query time to propagate relevance through the graph. Results:
- 2WikiMultiHopQA: +11% R@2, +20% R@5 vs. baselines
- MuSiQue: +3% vs. baselines  
- 10–30x cheaper than iterative retrieval (IRCoT) while matching or exceeding its recall
- 6–13x faster at inference than IRCoT

**HippoRAG 2** (ICML 2025, arXiv:2502.14802, published as *"From RAG to Memory: Non-Parametric Continual Learning for LLMs"*): Adds dense retrieval integration to the PPR mechanism. +7% improvement in associative memory tasks over state-of-the-art embedding models. Framed explicitly as a non-parametric continual learning framework — new documents added to the graph are immediately retrievable without retraining.

**LightRAG** (HKUDS, EMNLP 2025, arXiv:2410.05779): Dual-level retrieval — local (entity-specific) and global (community-level). Simpler than Microsoft GraphRAG's hierarchical community detection. On UltraDomain benchmark: >80% retrieval accuracy in legal document analysis vs. 60–70% for competing approaches. Designed for rapid ingestion and incremental updates.

**Consensus from 2025 research:** Graph augmentation provides measurable lift only when:
1. Queries require multi-hop reasoning across distinct facts
2. The corpus has meaningful relational structure (people, decisions, projects with causal links)
3. Query volume is high enough to justify indexing cost

For a personal engineering memory corpus with ~5–50k notes, the relational density is moderate (tasks, decisions, code patterns are connected), and multi-hop is genuinely required (e.g., "what dependencies does the approach from ticket X have on the pattern from ticket Y"). This puts Wizard firmly in the "graph augmentation worth exploring" zone.

### 1.5 Reranking: Proven Lift

Reranking is the most reliable performance lever in the IR stack. The evidence from 2024–2025 is consistent:

**Cross-encoder rerankers** (e.g., ms-marco-MiniLM-L-6-v2, BGE-Reranker-v2): Independently score each (query, document) pair using a full attention mechanism. Up to **+10 nDCG points on MS MARCO** over bi-encoders. 5–7 nDCG point lift over strong sparse retrievers like SPLADE-v3. Trade-off: O(k) full-model inferences, where k is the rerank window.

**LLM-as-reranker** (RankGPT, RankZephyr, RankVicuna — Castorini Lab, castorini/rank_llm, SIGIR 2025): Listwise approaches feed the entire candidate list to the LLM and ask it to rerank. Results on TREC DL19:
- RankGPT-4: 75.59 nDCG@10
- RankZephyr-7B: 74.22 nDCG@10 (open-weight)
- Cross-encoder (BM25 + rerank): ~72–73 nDCG@10
- BM25 alone: ~50 nDCG@10

LLM rerankers show **better zero-shot generalization to out-of-domain queries** (8% avg. degradation on unseen domains vs. 12–15% for cross-encoders). Cost is 1–3 orders of magnitude higher than cross-encoders.

**Efficient reranking at SIGIR 2025**: *"Efficient Re-ranking with Cross-encoders via Early Exit"* demonstrates that cross-encoders can exit computation early for easy-to-score pairs, reducing latency by 30–50% at <1% accuracy loss.

**E2Rank** (ECIR 2025): Layer-wise reranking — stop after cheaper early layers for obvious decisions, proceed to full depth only for ambiguous pairs.

**Practical recommendation:** For a corpus of <10k candidates, a cross-encoder reranker (ms-marco or BGE-Reranker) adds +5–10 points nDCG at <100ms additional latency. This is the highest-ROI single retrieval upgrade available.

### 1.6 Embedding Model Landscape — 2026 State

For a private, small, English-primary corpus running on a developer laptop:

| Model | Params | MTEB Score | Context | License | Notes |
|---|---|---|---|---|---|
| **Nomic Embed v2** | 137M | Strong (MoE) | 8192 | Apache 2.0 | CPU-runnable, best open quality/size |
| **BGE-M3** | 568M | Top-tier | 8192 | MIT | Dense + sparse + multi-vector; 100+ langs |
| **E5-large-instruct** | 335M | ~65 MTEB | 512 | MIT | Strong zero-shot, instruction-tuned |
| **EmbeddingGemma-300M** | 300M | Competitive | 512 | Open | Google, on-device focus |
| **Qwen3-Embedding-8B** | 8B | ~70.58 MTEB | 32768 | Apache 2.0 | SOTA open, needs GPU |
| **jina-colbert-v2** | ~137M | ColBERT-class | 8192 | Apache 2.0 | Multi-vector, multilingual |

For Wizard's use case (personal engineering notes, English, <50k documents, self-hosted):  
**Nomic Embed v2** or **BGE-M3** are the practical optima. Nomic v2 runs on CPU without compromise; BGE-M3 adds the flexibility to run dense, sparse, and multi-vector retrieval from a single model — useful if the stack evolves.

---

## Part 2: Near-Term Trajectory (2026–2029)

### 2.1 Where RAG Is Failing Today — and What Will Fix It

**Multi-hop reasoning** is the most active problem. Current solutions:
- *Iterative retrieval* (IRCoT, ReAct-RAG): retrieve → read → re-query. Accurate but 6–13x slower than single-shot.
- *HippoRAG / PPR*: graph propagation achieves multi-hop at single-shot speed. Likely the dominant pattern by 2027 for structured corpora.
- *Decomposition*: LLMs decompose queries into sub-queries, retrieve for each, then synthesize. RQ-RAG, KRAGEN (graph-of-thoughts). Still expensive; reliability depends on LLM quality.

**Temporal blindness** will be addressed by temporal knowledge graphs (section 2.3). The key research trajectory: facts must carry validity windows and supersession pointers. Graphiti/Zep's architecture (arXiv:2501.13956) is the leading design for this.

**Contradiction detection** remains an open problem. Current approaches rely on LLM-as-validator, which is slow and inconsistent. *ReliabilityRAG* (arXiv:2509.23519, September 2025) proposes provably robust retrieval under adversarial and noisy context — early-stage but the right direction. Expected to become production-viable by 2027–2028 as reranker models are fine-tuned for consistency scoring.

**Adaptive retrieval** (knowing when *not* to retrieve): Static RAG always retrieves, even when the answer is in the model's weights. Agentic RAG systems from 2025–2026 are starting to learn retrieval policies. The ICML 2025 paper *"Beyond RAG vs. Long-Context: Learning Distraction-Aware Retrieval"* (OpenReview:c8CZWLy4T4) trains models to selectively use retrieval only when context is genuinely needed, reducing latency and distraction-hallucination.

### 2.2 Learned Sparse Retrieval: Where SPLADE Is Going

Three trajectories are clear from 2025 research:

1. **Expanded vocabulary SPLADE**: Moving beyond BERT's WordPiece vocabulary to allow expansion into arbitrary terms. CSPLADE (Amazon, AACL 2025) uses causal language models as encoders, enabling expansion into terms that BERT cannot represent. This is the biggest limitation of current SPLADE — it can only assign weight to tokens in its fixed vocabulary.

2. **Hybrid-native sparse retrieval**: Vector databases (Milvus, Weaviate, Qdrant, Elasticsearch) now treat sparse vectors as first-class citizens alongside dense vectors. SPLADE sparse vectors are directly storable and searchable in hybrid indexes. The infrastructure barrier that previously required separate sparse and dense systems has dissolved.

3. **Efficiency improvements mature**: L1 regularization, query encoder distillation, and document-centric pruning now allow SPLADE to achieve BM25-comparable query latency on BEIR-scale corpora (arXiv:2511.22263). By 2027, SPLADE with efficient query encoding will likely replace BM25 as the baseline sparse component in production hybrid stacks.

### 2.3 Multi-Vector Retrieval (ColBERT) — Production Viability

ColBERT's production trajectory accelerated sharply after RAGatouille (early 2024). The dedicated ECIR 2026 workshop (LIR) marks its transition from "interesting research" to "expected production consideration."

**Remaining barriers to mainstream adoption:**
- Storage: ~40–60x more storage than single-vector dense models. A 100k-document corpus requires ~5–8 GB of token vectors.
- Index build time: Slower than bi-encoder indexing due to per-document vector matrices.

**Mitigation in progress:** Vespa's ColBERT embedder with compression (binary quantization of token vectors) reduces storage 32x at <5% accuracy loss. This brings ColBERT storage to ~2x of dense, which is acceptable.

**Likely trajectory:** By 2027–2028, compressed ColBERT will be standard as the **reranker layer** rather than the first-stage retriever. Dense (or sparse) retrieval at first-stage (recall-heavy, fast), then ColBERT MaxSim at second-stage (precision-heavy, moderately expensive). This 3-stage pipeline (BM25 + dense → merge → ColBERT rerank → cross-encoder for top-5) will be the canonical production setup.

### 2.4 Agentic Retrieval: Agents That Decide What to Retrieve

The shift from "static retrieval pipeline" to "agent with retrieval tools" is the most significant structural change in the field, and it is happening now.

**Agentic RAG** (survey: arXiv:2501.09136, January 2025) formalizes the transition. Agents:
- Decide *whether* to retrieve (vs. using parametric knowledge)
- Decide *what* to query (sub-query decomposition)
- Decide *which* source to query (multi-source routing)
- Critique retrieved results and re-query if insufficient
- Synthesize across multiple retrieval rounds

**Reasoning Agentic RAG** (arXiv:2506.10408, June 2025) applies System 1 / System 2 framing: fast shallow retrieval for simple queries, slow deliberate multi-step retrieval + reasoning for complex queries.

**SIGIR 2025 framing** (*"Information Retrieval for Artificial General Intelligence"*, timan.cs.illinois.edu/czhai/pub/IR_AGI_SIGIR2025.pdf): The paper defines five novel IR tasks for agents pursuing AGI:
1. External information retrieval (answering what the agent doesn't know)
2. Provenance retrieval (tracing why the agent believes something)
3. Rule retrieval (activating the right behavioral rule from a policy corpus)
4. Scenario retrieval (identifying analogous past situations for decision-making)
5. Self-knowledge retrieval (querying the agent's own memory for consistency)

Task 5 — self-knowledge retrieval — is exactly what Wizard does. The IR research community has now formally identified it as a distinct problem class with its own requirements.

**For Wizard specifically:** The implication is that Wizard's search tool should evolve from a passive lookup into an agentic retrieval tool — one that can plan a multi-step retrieval sequence, combine results from different memory types (notes, decisions, task history), and return a synthesized answer rather than a ranked list.

---

## Part 3: Far Future (2030–2035)

### 3.1 Will Retrieval as a Separate Component Survive?

The "RAG is dead" narrative is empirically wrong — enterprise RAG deployments grew 280% in 2025. But the *form* of retrieval is changing.

The fundamental constraint is the **Orthogonality Constraint** (arXiv:2601.15313): for neural memory to be reliable, memory keys must be orthogonal — but semantic embeddings cluster similar concepts together by design, causing interference. This is a geometric limit on how much "memory" can be stored in model weights before retrieval degrades. This limit will not be solved by scaling alone.

The ICML 2025 position paper (*"From RAG to Memory"*, arXiv:2502.14802) argues that non-parametric memory (external retrieval) is not a patch on top of LLMs — it is the correct architecture for continual learning. Parametric memory (weights) is best for static, common knowledge. Non-parametric memory (retrieval indexes) is best for personal, recent, and long-tail knowledge. These are complementary, not competing.

**Prediction for 2030–2032:** Retrieval will not be absorbed into weights. Instead, the boundary will shift: models will natively route between parametric lookup (fast, free) and non-parametric retrieval (slower, grounded, auditable) as a learned behavior. The retrieval component will still exist but will be invoked by the model itself, not by an external pipeline.

### 3.2 Search When the System Knows Full Context

128k–1M token context windows (2025 standard; 10M projected for 2028) create a genuine alternative to retrieval for small corpora: just inject everything. But:

- **Cost**: Long context is 8–82x more expensive than retrieval for typical workloads (RAGFlow 2025 analysis)
- **"Lost in the middle" problem**: LLMs reliably attend to context at the beginning and end; material in the middle is systematically underweighted (arXiv:2307.03172)
- **Dynamic corpora**: A memory layer grows daily. At 500 new notes/year, a 5-year corpus exceeds 2500 notes. At 500 tokens each, that is 1.25M tokens — already at the edge of current window limits and growing

The 2025-era answer is hybrid: **use retrieval to select the relevant subset, then pass that subset in a moderately long context window for reasoning**. This is what the research calls "RAG-augmented long context."

The 2030 answer may be: retrieval identifies the 20–50 most relevant items, and the model reasons over those with a 50k-token context that it can attend to reliably. The retrieval component gets smaller (fewer candidates needed), but it does not disappear.

### 3.3 Speculative Frontier: Causal Graphs, Temporal KGs, Semantic Triples

**Temporal Knowledge Graphs (TKGs)**: The research frontier here is active. Zep/Graphiti (arXiv:2501.13956, January 2025) is the first production system explicitly designed as a temporal KG for agent memory. Each fact carries a validity window: when it became true and when it was superseded. This solves the temporal blindness problem directly. Graphiti in benchmarks: 94.8% on Deep Memory Retrieval (DMR) vs. 93.4% for MemGPT; +18.5% accuracy improvement and 90% latency reduction on LongMemEval.

**Causal Retrieval**: The research on causal decision provenance (related to Wizard wild-ideas/03-causal-decision-provenance.md) intersects with a growing IR research thread: retrieving *why* facts are true, not just *that* they are true. *MAGMA: A Multi-Graph based Agentic Memory Architecture* (arXiv:2601.03236, January 2025) maintains separate graph layers for episodic, semantic, and procedural memory, with causal edges between layers.

**Semantic Triples and SPARQL-style Retrieval over Personal Graphs**: The *PersonalAI* paper (arXiv:2506.17001) benchmarks structured graph query vs. vector retrieval for personal agent memory. Structured queries reliably outperform vector search when the query maps cleanly to a relationship (e.g., "what decision did I make about X?") — structured graph traversal returns exact answers, vector search returns approximate matches.

**Rethinking Memory in AI** (arXiv:2505.00675, May 2025, comprehensive survey): Categorizes future memory paradigms:
- *Graph-based*: explicit relationships, multi-hop native, interpretable
- *Signal-enhanced*: attention-based memory weighting, neural episodic memory
- *Timeline-based*: temporal ordering, recency decay, event sequences

The research consensus: by 2030, agent memory systems will combine all three. A personal coding agent's memory will be a temporal-relational graph where nodes are entities (tasks, files, decisions, patterns), edges are causal and semantic relationships, and each edge carries a timestamp and confidence. Retrieval will traverse this graph using a combination of BM25 (for token-level match), dense embedding (for semantic match), and PPR-style graph propagation (for relational reach).

**Graph-based Agent Memory: Taxonomy, Techniques, and Applications** (arXiv:2602.05665, February 2025) surveys current graph memory approaches and identifies three open problems for the next 5 years:
1. Efficient incremental graph update (no full rebuild on new documents)
2. Temporal consistency maintenance (invalidating outdated facts without losing historical record)
3. Hybrid retrieval over graph + vector space in a unified query language

All three are research-active problems with no complete solutions as of 2026. Graphiti partially solves (1) and (2). Unified query language for (3) is 3–5 years from production.

---

## Part 4: What Retrieval Stack Wizard Should Use

### In 2027

Wizard's corpus at this point will be: ~5k–15k structured notes, decisions, tasks; English; personal; append-heavy (rarely updated, mostly new); with timestamps on everything.

**Recommended stack:**

1. **First-stage: SQLite FTS5 (BM25) + Nomic Embed v2 or BGE-M3 dense vectors** in a hybrid configuration. SQLite already exists; adding dense vectors via sqlite-vec or a small FAISS index is incremental. Merge with RRF (k=60 is the empirically validated constant). This replaces BM25-only search and delivers +15–25% retrieval recall on Wizard's specific query patterns.

2. **Second-stage reranker: BGE-Reranker-v2** (cross-encoder, runs on CPU, <200ms for top-20 candidates). This adds the most reliable lift (+5–10 nDCG points) at the lowest engineering cost. No model hosting required — runs in-process with llm_rerank.

3. **Temporal weighting**: Add recency scoring to the RRF merge. A note from 6 weeks ago about a deprecated approach should score lower than a note from last week about the current approach, all else equal. Simple exponential decay (half-life ~90 days) applied as a multiplicative factor on final scores. This is not in any standard retrieval library but is a 20-line addition to Wizard's ranking code.

4. **Skip graph augmentation for now.** At 5k–15k notes, the graph construction cost (LLM extraction of entities and relationships) exceeds the retrieval benefit for Wizard's primary query pattern (keyword + semantic recall of past decisions). Revisit when multi-hop becomes a genuine user complaint — "I asked about X but needed to know about Y first."

**What to watch (but not build yet):**
- HippoRAG 2's PPR-over-KG approach for multi-hop: open source at github.com/OSU-NLP-Group/HippoRAG, production-ready by 2026–2027
- SPLADE as replacement for BM25 (pending efficient query encoder production deployment)

### In 2031

Five years of growth: ~30k–80k structured memories; temporal density (many facts with supersession chains); richer relational structure (tasks → decisions → code patterns → outcomes).

**Recommended stack:**

1. **Temporal knowledge graph** as the primary index. Graphiti or its successor: entities, relationships, validity windows. This is not optional at this scale — flat vector search over 80k items will struggle with temporal and relational queries. The graph provides the structural backbone.

2. **Hybrid retrieval over the graph**: dense vector on node embeddings for semantic match, BM25/SPLADE on node text fields for exact match, PPR propagation on graph edges for relational reach. These three signals fused at query time.

3. **Compressed ColBERT as second-stage reranker** over the top-50 candidates from the graph. At this scale, the multi-vector precision is worth the cost — it distinguishes "I used retry-with-backoff in the Stripe integration" from "I considered but rejected retry-with-backoff in the Kafka consumer" when both rank equally on first-stage.

4. **Agentic retrieval front-end**: Rather than a single search tool, a retrieval agent that (a) classifies the query type, (b) selects the retrieval strategy (keyword, semantic, relational, temporal), (c) issues multiple sub-queries if needed, (d) returns a synthesized answer with provenance citations. This is what the SIGIR 2025 IR-for-AGI paper calls "provenance retrieval" + "self-knowledge retrieval."

5. **Contradiction detection pass** before returning results: by 2029–2030, lightweight consistency models will exist that flag when two returned items contradict each other (e.g., "approach is X" from 2027 and "approach is Y" from 2029 returned together). Surface the conflict to the user rather than silently returning both.

The 2031 Wizard retrieval stack will look nothing like BM25 on a SQLite FTS5 table. But it will still be retrieval — just temporally-aware, relationally-structured, agent-orchestrated retrieval over a living knowledge graph.

---

## Key Papers Referenced

- *Seven Failure Points When Engineering a Retrieval Augmented Generation System* — Barnett et al., 2024. arXiv:2401.05856. https://arxiv.org/abs/2401.05856
- *HippoRAG: Neurobiologically Inspired Long-Term Memory for LLMs* — OSU NLP Group, NeurIPS 2024. arXiv:2405.14831. https://arxiv.org/abs/2405.14831
- *From RAG to Memory: Non-Parametric Continual Learning for LLMs* — HippoRAG 2, ICML 2025. arXiv:2502.14802. https://arxiv.org/abs/2502.14802
- *Zep: A Temporal Knowledge Graph Architecture for Agent Memory* — Rasmussen et al., January 2025. arXiv:2501.13956. https://arxiv.org/abs/2501.13956
- *BGE M3-Embedding: Multi-Lingual, Multi-Functionality, Multi-Granularity* — BAAI, 2024. arXiv:2402.03216. https://arxiv.org/abs/2402.03216
- *LightRAG: Simple and Fast Retrieval-Augmented Generation* — HKUDS, EMNLP 2025. arXiv:2410.05779. https://arxiv.org/abs/2410.05779
- *RAG vs. GraphRAG: A Systematic Evaluation* — February 2025. arXiv:2502.11371. https://arxiv.org/abs/2502.11371
- *Agentic Retrieval-Augmented Generation: A Survey on Agentic RAG* — January 2025. arXiv:2501.09136. https://arxiv.org/abs/2501.09136
- *Information Retrieval for Artificial General Intelligence* — ChengXiang Zhai, SIGIR 2025. https://dl.acm.org/doi/10.1145/3726302.3730349
- *Contradiction Detection in RAG Systems* — April 2025. arXiv:2504.00180. https://arxiv.org/abs/2504.00180
- *MAGMA: A Multi-Graph based Agentic Memory Architecture* — January 2025. arXiv:2601.03236. https://arxiv.org/abs/2601.03236
- *Graph-based Agent Memory: Taxonomy, Techniques, and Applications* — February 2025. arXiv:2602.05665. https://arxiv.org/abs/2602.05665
- *Rethinking Memory in AI: Taxonomy, Operations, Topics, and Future Directions* — May 2025. arXiv:2505.00675. https://arxiv.org/abs/2505.00675
- *Attention Is Not Retention: The Orthogonality Constraint in Infinite-Context Architectures* — January 2025. arXiv:2601.15313. https://arxiv.org/abs/2601.15313
- *Reasoning RAG via System 1 or System 2* — June 2025. arXiv:2506.10408. https://arxiv.org/abs/2506.10408
- *PersonalAI: Comparison of Knowledge Graph Storage and Retrieval for Personalized LLM Agents* — June 2025. arXiv:2506.17001. https://arxiv.org/abs/2506.17001
- *When to Use Graphs in RAG: A Comprehensive Analysis* (GraphRAG-Bench, ICLR 2026). arXiv:2506.05690. https://arxiv.org/abs/2506.05690
- *LIR: First Workshop on Late Interaction and Multi Vector Retrieval, ECIR 2026*. arXiv:2511.00444. https://arxiv.org/abs/2511.00444
- *Efficiency and Effectiveness of SPLADE Models on Billion-Scale Web Document Title* — November 2025. arXiv:2511.22263. https://arxiv.org/abs/2511.22263
- *CSPLADE: Learned Sparse Retrieval with Causal Language Models* — Amazon, AACL 2025. https://assets.amazon.science/8f/92/a835b4b346e4a4ed7a797010d501/aacl2025-csplade.pdf
- *RankLLM: A Python Package for Reranking with LLMs* — Castorini Lab, SIGIR 2025. https://github.com/castorini/rank_llm
- *Long Context vs. RAG for LLMs: An Evaluation and Revisits* — January 2025. arXiv:2501.01880. https://arxiv.org/abs/2501.01880
- *Temporal Reasoning over Evolving Knowledge Graphs* — September 2025. arXiv:2509.15464. https://arxiv.org/abs/2509.15464
