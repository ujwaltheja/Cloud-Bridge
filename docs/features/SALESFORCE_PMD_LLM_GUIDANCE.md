# IBM Salesforce PMD Remediation Guidance

## Purpose
This document is the grounding knowledge base for IBM-only PMD review and remediation guidance.
It is intended to support:
- pre-deployment PMD checks
- LLM-generated remediation suggestions
- PDF reporting for PMD findings
- retrieval of rule-specific guidance for exact Apex classes and metadata files

## Core PMD Review Principles
1. Fix high-severity issues before validation or deployment.
2. Prefer exact code-level remediation over generic advice.
3. Preserve business behavior while improving maintainability and security.
4. Prioritize Apex security, bulkification, null safety, and testability.
5. Treat repeated violations in the same class as a structural refactor signal.

## Common Salesforce PMD Rule Categories

### 1. Apex Security
Typical concerns:
- CRUD/FLS checks missing
- unsafe dynamic SOQL
- unsafe DML patterns
- sharing model misuse

Recommended remediation:
- enforce object and field access checks before read/write operations
- use bind variables instead of string-built SOQL
- prefer `with sharing` where appropriate
- isolate privileged operations in reviewed service layers

LLM guidance pattern:
- identify the exact method and query
- explain why the current implementation is unsafe
- propose a minimal safe rewrite
- mention any required helper utility or selector/service abstraction

### 2. Performance and Bulkification
Typical concerns:
- SOQL inside loops
- DML inside loops
- repeated expensive operations
- non-bulk-safe trigger logic

Recommended remediation:
- move queries outside loops
- aggregate records before DML
- use maps and sets for lookups
- centralize trigger orchestration in handler classes

LLM guidance pattern:
- point to the exact loop or trigger block
- describe governor-limit risk
- suggest collection-based refactor
- preserve current business logic ordering

### 3. Code Style and Maintainability
Typical concerns:
- excessive class length
- high cyclomatic complexity
- deeply nested conditionals
- duplicated logic
- unused variables or methods

Recommended remediation:
- extract helper methods
- split responsibilities into service/domain/helper classes
- reduce nesting with guard clauses
- remove dead code after confirming no references

LLM guidance pattern:
- identify the exact method or block
- explain maintainability impact
- propose method extraction or class split
- keep naming aligned with Salesforce domain language

### 4. Error Handling and Reliability
Typical concerns:
- swallowed exceptions
- generic catch blocks
- missing logging context
- unsafe null assumptions

Recommended remediation:
- catch specific exceptions where possible
- log actionable context
- fail gracefully with meaningful messages
- add null guards and defensive checks

LLM guidance pattern:
- identify the exact catch block or null-sensitive line
- explain operational risk
- propose safer exception handling and guard clauses

### 5. Testability and Design
Typical concerns:
- hard-coded dependencies
- logic tightly coupled to trigger context
- missing seams for mocking
- mixed orchestration and business logic

Recommended remediation:
- extract injectable collaborators where practical
- separate trigger routing from business logic
- isolate selectors, services, and domain logic
- make methods deterministic and easier to test

LLM guidance pattern:
- identify the exact dependency or coupling issue
- propose a small refactor that improves testability
- mention likely unit-test improvements

## IBM Reporting Expectations
For every PMD finding, generated guidance should include:
- impacted file or class
- rule name
- severity
- business risk summary
- exact remediation suggestion
- optional code-level fix direction
- deployment recommendation impact

## Suggested Severity Interpretation
- Priority 1: security or deployment-blocking issue
- Priority 2: high-risk maintainability or governor-limit issue
- Priority 3: medium-risk quality issue
- Priority 4: low-risk cleanup or style issue

## LLM Prompting Expectations
When generating remediation:
1. Use the exact file path and class name.
2. Reference the exact PMD rule.
3. Use the source snippet if available.
4. Recommend the smallest safe fix first.
5. Avoid speculative changes outside the flagged scope.
6. Explain impact on deployment readiness for IBM reviewers.

## Example Remediation Shape
- Finding: `AvoidSoqlInLoops`
- File: `force-app/main/default/classes/OpportunitySync.cls`
- Guidance:
  - Move the SOQL query outside the loop.
  - Collect record identifiers in a set first.
  - Query related records once.
  - Re-map results by Id before iterating.
  - This reduces governor-limit risk and improves deployment safety.

## Reuse Notes
This document may be chunked and retrieved by keyword, rule name, severity, or category.
Preferred retrieval keys:
- PMD rule name
- Apex security
- bulkification
- maintainability
- exception handling
- testability