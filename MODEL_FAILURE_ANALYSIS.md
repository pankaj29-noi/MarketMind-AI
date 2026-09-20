# MODEL_FAILURE_ANALYSIS

**Date:** 2026-09-21  
**Scope:** Patterns observed from prior LangGraph E2E captures + static code review.  
**Policy:** Do **not** fine-tune until failure categories are quantified on the 100-Q NL suite with live providers.

---

## Observed failure / cost categories

| Category | Evidence | Mitigation in this upgrade |
|---|---|---|
| Schema misunderstanding via MCP | ~10.8s MCP fail on CSV sessions | In-process rich profile (already landed) |
| Metric misunderstanding (`sales` vs revenue) | Requirement aliases + ambiguous concepts | `question_ir` flags ambiguity; abstain notes |
| Missing profit column | Unsupported asks | Explicit unsupported notes in IR |
| Aggregation / ranking errors | Retry loops in medium E2E (~197s, 3 retries) | One-shot repair cap; pattern library |
| Denominator / share errors | Hard questions in suite | Ground-truth SQL templates; coverage checks |
| Filter omission | Semantic validator failures | `requirement_coverage` + result validation |
| Hallucinated columns | SQL quality validator | Column existence checks |
| Excess LLM calls on SIMPLE | Planner+codegen+viz+report | Fast-path deterministic plan/SQL; skip SIMPLE viz |
| False LIMIT on QUALIFY | Prior validator | Fixed window top-N acceptance |

---

## Fine-tuning decision

**Not recommended yet.**

Reason: deterministic layers (profile, IR, patterns, coverage, DuckDB) still have headroom. Fine-tuning would overfit and fight the “DATABASE RESULT > LLM MEMORY” principle.

Revisit only after a scored NL→SQL run of the 100-Q suite records:

- ≥20 consistent failures in one category
- after fast-path + one-shot repair are deployed

---

## Next measurement needed

Instrument true LLM call counts per node and run a controlled Groq sample (easy/medium/hard/very_hard × 5) without fabricating results.
