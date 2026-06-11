# Roadmap Items 1 2 3 5 Progress

Session anchor:
- date: 2026-06-09
- roadmap: `docs/product-roadmap.md`
- scoring: `docs/product-roadmap-scoring.md`
- plan: `docs/superpowers/plans/2026-06-09-roadmap-items-1235.md`

## Scope

Implemented / verified scoring items:

1. Repeated-idea lineage/status-aware review
2. Adaptive format decision artifact
3. `tw` as personal scribe / natural dictation entry
5. Manual high-value interaction analytics

Item 4, evidence-based risk detector, remains the next major quality item.

## Completed

### Item 1: repeated-idea status-aware review

Status:
- completed before this pass
- verified during this pass

Behavior:
- captured ideas do not count as repeated audience exposure
- ordinary draft drafts do not count
- ready/posted drafts and posts still count

Tests:
- `tests/test_algorithm_review.py`

### Item 2: format decision artifact

Added:
- `twitter_content_machine/format_decision.py`
- per-draft `FORMAT_DECISION.md`
- `format_decision` block in `13_context_bundle.json`
- format decision section in `13_context_bundle.md`
- format decision section in `14_llm_request.md`

Behavior:
- explicit user formats are recorded as `decision_source: explicit-user-format`
- default adaptive mode records `decision_source: adaptive-heuristic`
- heuristics choose among `short`, `adaptive-single`, `thread`, `build-log`,
  `article-note`, and `question`

### Item 3: personal scribe entry

Added:
- bare `tw "<dictated instruction>"` normalization

Behavior:
- if the first arg is a known command, normal CLI behavior stays unchanged
- if the first arg is a multi-word unknown text or multiple non-command args,
  it becomes `tw draft ...`
- a single unknown token still errors, which protects common command typos

### Item 5: manual high-value interaction analytics

Added:
- `twitter_content_machine/outcomes.py`
- `twitter_content_machine/commands/outcome_ops.py`
- `tw outcome`
- `tw outcomes`
- MCP wrappers `tw_record_outcome`, `tw_list_outcomes`
- SQLite tables:
  - `accounts`
  - `high_value_interactions`
- per-draft artifact:
  - `20_high_value_interactions.md`

Example:

```powershell
tw outcome latest --handle @quantdev --action reply --why "quant dev with relevant benchmark work" --cluster quant --relationship builder --follow-up
tw outcomes
```

## Tests Added

- `test_adaptive_draft_writes_format_decision_artifact`
- `test_explicit_short_format_records_user_override`
- `test_bare_tw_text_creates_adaptive_draft`
- `test_outcome_command_records_high_value_interaction`
- `test_outcomes_command_lists_current_draft_interactions`

## Verification

Focused:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest tests/test_algorithm_review.py tests/test_drafting_workflow.py tests/test_active_draft_cli.py tests/test_outcomes.py tests/test_memory_x_mcp.py -q
```

Result:
- `36 passed`

Full suite:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q
```

Result:
- `56 passed`

## Next

Next roadmap item:
- evidence-based risk detector

Reason:
- now draft format and manual outcome feedback exist
- detector trust remains the biggest quality gap
