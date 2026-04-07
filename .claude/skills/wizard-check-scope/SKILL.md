---
name: wizard-check-scope
description: >
  Use when you want to check for out-of-scope or removed components in the Wizard codebase.
  Detects implementations that were explicitly removed from v2 or listed as out of scope in
  SPEC_v6. Invoke with /wizard-check-scope.
---

# Out-of-Scope & Removed Component Detection

Check the Wizard codebase for components that were explicitly removed from v2 (SPEC_v6 §11) or declared out of scope (SPEC_v6 §16). Report findings in the format below.

## What To Check

### 1. Removed Components (SPEC_v6 §11)

These were designed then explicitly removed. They must not appear in the codebase:

**Queues and DLQ:**
- Search for `queue`, `Queue`, `DLQ`, `dead.letter`, `bull`, `bullmq`, `amqp`, `rabbitmq`, `kafka`, `SQS`, `background.job`, `worker.thread` in all `.ts` files (excluding `node_modules/` and `docs/`).
- Any implementation of queue or background job infrastructure is a FAIL. References in comments explaining why they were removed are fine.

**Exaggeration detection:**
- Search for `exaggerat` in all `.ts` files.
- Any implementation is a FAIL.

**Hallucination detection:**
- Search for `hallucin` in all `.ts` files.
- Any implementation is a FAIL. Note: attribution check via pgvector similarity is allowed and distinct — it lives in the output pipeline as a data integrity check, not a hallucination detector.

**Full eval framework:**
- Check the `evals/` directory. It should contain scaffold only — dataset format definition and a runner stub.
- If `evals/` contains working evaluation pipelines, scoring logic, or model comparison infrastructure, that is a FAIL. Scaffold = type definitions + empty runner.

**Four code intelligence structures:**
- Search for `LSPSymbol`, `TreeSitter`, `tree.sitter`, `call.map`, `CallMap`, `call.graph`, `CallGraph`, `inheritance.map`, `InheritanceMap`, `AST` (as a type/class, not in comments) in all `.ts` files.
- Any implementation is a FAIL. `CodeChunkEmbedding` and Serena live traversal are the correct replacements.

### 2. Out of Scope (SPEC_v6 §16)

These are explicitly out of scope for v2:

**Hosting / cloud / multi-tenancy:**
- Search for `deploy`, `Dockerfile` (beyond docker-compose for local Postgres), `kubernetes`, `k8s`, `terraform`, `AWS`, `GCP`, `Azure`, `tenant`, `multi.tenant` in `.ts` files and config files.
- Local Docker for Postgres is fine. Cloud deployment infrastructure is a FAIL.

**PII stubbing/replacement:**
- Search for `[REDACTED]`, `[REMOVED]`, `***`, `placeholder`, `stub` in `security/` code that deals with PII.
- PII must be scrubbed (removed entirely), not stubbed/replaced. Any replacement logic is a FAIL.

**Dynamic workflow definitions:**
- Search for code that loads workflow definitions from a database, config file, or external source in `core/` or `orchestrator/`.
- Workflows must be hardcoded in `core/`. Dynamic loading is a FAIL.

**Authentication/auth middleware:**
- Search for `auth`, `jwt`, `token.verify`, `session.token`, `passport`, `bcrypt`, `password` in all `.ts` files (excluding `integrations/` where API tokens for external services are expected).
- The `User` model exists but auth is deferred. Any auth middleware or login flow is a FAIL.

**Clinical data handling:**
- Search for `clinical`, `patient`, `diagnosis`, `prescription`, `medical.record`, `NHS.record` in all `.ts` files.
- Any pipeline that processes clinical data is a FAIL. Engineering context only in v2.

**Semantic threshold auto-calibration:**
- Search for `auto.calibrat`, `self.calibrat`, `adaptive.threshold` in all `.ts` files.
- Calibration is a manual process in v2. Any automatic recalibration logic is a FAIL.

**Billing / licensing / commercial infrastructure:**
- Search for `billing`, `license`, `subscription`, `payment`, `stripe`, `invoice` in all `.ts` files.
- Any commercial infrastructure is a FAIL.

**LSP integration directly in Wizard:**
- Search for `lsp`, `language.server`, `LSPClient` in all `.ts` files (excluding references to Serena).
- Serena provides the LSP bridge. Direct LSP integration in Wizard is a FAIL.

## Output Format

```
## Scope Check

### PASS — No removed components
### FAIL — Out of scope (1 issue)
- security/scrubber.ts:28 — PII stubbing with [REDACTED] instead of scrubbing

Result: PASS / FAIL
```
