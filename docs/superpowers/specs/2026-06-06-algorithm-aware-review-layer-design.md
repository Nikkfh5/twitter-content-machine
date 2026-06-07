# Algorithm-Aware Review Layer Design

Session anchor:
- date: 2026-06-06
- repo: `C:\N\hse\twitter-content-machine`
- base_commit: `4d791cd`
- feature_id: `algorithm-aware-review-layer`

## Verdict

Idea strength: strong.

The real edge is not "hack the algorithm". The edge is forcing each draft to
answer:

> For which viewer cluster is this clearly relevant, what action could it
> reasonably trigger, and what negative feedback risk does it create?

## Scope

Build Stage 1 only: local heuristic review layer. No X API import, no peer
analysis, no autopublish, no new publish-like MCP tool.

## Architecture

Add a focused module, `twitter_content_machine.algorithm_review`, responsible
for:

- resolving a draft folder through existing `get_draft()` / `resolve_draft_id()`
- reading `06_final_candidate.md`, draft metadata, and related memory
- scoring X-fit with local heuristics
- writing review files into the draft folder

Keep CLI orchestration in `twitter_content_machine.cli`. Keep safety string and
no-publish contract intact.

## Commands

### `tw algo-review <draft_id|latest>`

Writes `07_algorithm_review.md`.

Output sections:

1. Candidate retrieval fit
2. Primary predicted action
3. Secondary predicted action
4. Negative feedback risk
5. Format fit
6. Media fit
7. Revision instructions
8. Decision
9. Machine-readable scores

Decision rule:

- publish candidate: total >= 22 and no high safety risk
- revise: total 16-21 or medium fixable risk
- reject: total < 16 or high safety risk

The label is "publish candidate" because a human may manually post later. The
tool itself never posts.

### `tw media-plan <draft_id|latest>`

Writes `08_media_plan.md`.

Media is recommended only when it adds information and could increase
photo_expand, dwell, or share:

- chart
- diagram
- terminal screenshot
- table
- code/output snippet
- annotated plot

Decorative media must be rejected.

### `tw distribution-plan <draft_id|latest>`

Writes `09_distribution_plan.md`.

Recommends:

- standalone
- reply
- quote
- thread

Also records initial audience, useful follow-up reply, and do-not-do list.

### `tw draft --algo-aware ...`

Runs normal draft creation, then writes all three review files.

For Stage 1, variants stay mostly compatible with the current generator, but
`--algo-aware` adds the downstream review and planning artifacts. Later versions
can generate action-targeted variants.

## Workspace Defaults

Extend `ensure_workspace()` profile defaults:

- `profile/x_algorithm_principles.md`
- `profile/x_fit_rubric.yaml`

Existing profile files must not be overwritten.

## Heuristics

Topic clusters:

- quant / markets / microstructure
- C++ / systems / ML infra
- build logs: backtesting, CPD, market data, experiments
- learning notes: misunderstood, broke, changed

Primary positive actions:

- reply
- repost/share
- dwell
- photo_expand
- video_view
- profile_click
- follow_author
- click

Negative actions:

- not_interested
- block_author
- mute_author
- report

Anti-patterns:

- crypto shilling
- "alpha", "100x", "easy money"
- financial advice
- "not financial advice" used as a shield
- fake contrarian hooks
- engagement bait such as "thoughts?" or "agree?"
- generic AI/ML takes
- overclaiming
- generic motivational endings
- repeated ideas

## Tests

Use existing pytest setup:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q
```

Add tests to `tests/test_core_workflow.py` unless file size becomes a problem.

Required coverage:

- `tw algo-review latest` creates `07_algorithm_review.md`
- `tw media-plan latest` creates `08_media_plan.md`
- `tw distribution-plan latest` creates `09_distribution_plan.md`
- `tw draft --algo-aware --short ...` creates all three review files
- MCP tool registry still has no publish tool
- repeated idea is flagged
- crypto / financial-advice wording is flagged
- decorative media is not suggested
- weak thread stretched from one idea is rejected or revised

## Out Of Scope

- `tw analyze-peer`
- `tw analyze-own --sync`
- `tw experiment-log`
- `tw anti-spam`
- any X write API
- any browser automation that clicks Post
- any production-weight claim about X ranking

