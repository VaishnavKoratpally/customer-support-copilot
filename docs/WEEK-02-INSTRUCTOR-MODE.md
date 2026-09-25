# Week 02 Instructor Mode (Deep Learning Protocol)

Use this protocol for every Week 02 commit.  
Goal: you should be able to explain every line, every tradeoff, and every validation result.

## 1) Commit framing (before any code)

For each micro-commit, write:
1. **Objective**: what exact capability this commit adds.
2. **Boundary**: what this commit explicitly does *not* change.
3. **Why now**: why this is the next logical step in the architecture sequence.
4. **Alternatives considered**: at least 2 options and why one was chosen.

If objective or boundary is unclear, do not code yet.

## 2) Line-by-line understanding requirement

For each touched file, use this checklist:
- What does each new line do?
- Why is this line here?
- What breaks if we remove this line?
- Why this approach vs alternative?

Minimum standard:
- explain all imports,
- explain all new function signatures,
- explain all conditionals,
- explain all returned fields.

## 3) Runtime verification requirement

Every commit must include:
1. **Compile/syntax check**
2. **One behavior check** (API call/script/test)
3. **One failure-mode check** when applicable
4. **Observed output evidence** (command output or artifact)

No commit is complete without verification evidence.

## 4) Tradeoff narration template

For each decision, capture:
- **Benefit**
- **Cost**
- **Risk**
- **Rollback trigger**

Example:
- Benefit: real model path validates realistic latency/quality.
- Cost: increased runtime variability.
- Risk: non-deterministic outputs affect evaluator stability.
- Rollback trigger: if baseline latency regresses beyond threshold, fall back to stub path while preserving interfaces.

## 5) Question prompts you must answer after each commit

1. What changed technically?
2. Why is this better than before?
3. What risk did we introduce?
4. How did we verify behavior?
5. What should be measured next?

## 6) Week 02 commit execution style

Each commit should be:
- **incremental**
- **single-purpose**
- **reversible**
- **observable**

Avoid bundling unrelated changes.

## 7) Architecture posture for Week 02

Week 02 is runtime integration week:
1. Real model path (Ollama)
2. Real persistence path (Postgres)
3. Practical Redis integration
4. Quality evaluators and baseline deltas

This order is intentional: realism first, optimization second.

## 8) Definition of “I truly understood this commit”

You can:
- explain request flow and data flow end-to-end from memory,
- justify each tradeoff made,
- predict likely failure modes before they happen,
- describe how to detect and recover from those failures.

