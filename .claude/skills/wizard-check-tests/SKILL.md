---
name: wizard-check-tests
description: >
  Use when you want to check for empty, placeholder, or weak tests in the Wizard codebase.
  Detects it.todo(), empty test bodies, weak-only assertions, and mock-heavy tests that don't
  verify behavior. Invoke with /wizard-check-tests.
---

# Empty & Placeholder Test Detection

Check the Wizard test suite for tests that look like progress but assert nothing. Report findings in the format below.

## What To Check

### 1. Todo Tests

**How to check:**
- Use Grep to search for `it\.todo\(`, `test\.todo\(`, `xit\(`, `xtest\(`, `it\.skip\(`, `test\.skip\(` in all `.ts` files under `tests/`.
- Each match is a FAIL. Tests must be implemented or removed, not left as todos.

### 2. Empty Test Bodies

**How to check:**
- Use Grep with multiline mode to search for test bodies that are empty or contain only trivially true assertions.
- Patterns to catch:
  - `test\(.*,\s*\(\)\s*=>\s*\{\s*\}\)` — empty arrow function body
  - `test\(.*,\s*function\s*\(\)\s*\{\s*\}\)` — empty function body
  - `expect(true).toBe(true)` or `expect(1).toBe(1)` as the only assertion
- Each match is a FAIL.

### 3. Weak-Only Assertions

A test that only asserts existence without checking actual values is a placeholder in disguise.

**How to check:**
- For each test block (`it(` or `test(`), check if the ONLY expect statements are:
  - `expect(...).toBeDefined()`
  - `expect(...).toBeTruthy()`
  - `expect(...).not.toBeNull()`
  - `expect(...).not.toBeUndefined()`
- If a test has ONLY these weak assertions and no specific value/property assertions, it is a FAIL.
- If a test has weak assertions PLUS specific assertions (e.g., `expect(result.id).toBe(1)`), that is fine — the weak assertion is just a guard.

### 4. Empty Describe Blocks

**How to check:**
- Use Grep with multiline mode to find `describe(` blocks that contain no `it(` or `test(` children.
- Each match is a FAIL.

### 5. Mock-Heavy Tests

Tests that mock the thing they're supposed to test.

**How to check:**
- For each test file, check if the primary module under test is mocked. For example:
  - A test for `TaskRepository` that mocks `TaskRepository` — FAIL.
  - A test for `TaskService` that mocks the repository it calls — fine (testing service logic, not repository).
- Also flag tests where more than half the test body is mock setup and the actual assertion is trivial.
- This check requires reading the test files and understanding what they test. Use judgement.

## Output Format

```
## Test Quality Check

### FAIL — Todo tests (2 issues)
- tests/contracts/data-to-mcp.test.ts:15 — it.todo("should return null for missing task")
- tests/unit/skill-injection.test.ts:8 — test.skip("template rendering")

### PASS — No empty test bodies
### FAIL — Weak-only assertions (1 issue)
- tests/contracts/data-to-mcp.test.ts:22 — only asserts toBeDefined(), no value checks

### PASS — No empty describe blocks
### PASS — No mock-heavy tests

Result: PASS / FAIL
```
