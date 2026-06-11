# Algorithm-Aware Content Layer: Ideas And Backlog

Session anchor:
- date: 2026-06-06
- repo: `C:\N\hse\twitter-content-machine`
- base_commit: `4d791cd`
- feature_id: `algorithm-aware-review-layer`

Top-level roadmap:
- `docs/product-roadmap.md`

## Core Idea

Add an algorithm-aware review layer to the local draft-only X/Twitter content
machine.

The goal is not generic virality. The goal is to make each draft a clean
candidate for the right personalized recommendation audience:

1. clear topic / audience fit
2. likely positive action from the right viewer
3. low negative feedback risk
4. correct format and media choice
5. stable account positioning around markets, systems, ML infra, and build logs

The tool must stay draft-only. It must never publish automatically, never expose
a publish tool, and never recommend spam, fake controversy, financial advice, or
manipulative engagement bait.

## Source-Informed Model

Treat X For You as a personalized recommendation pipeline, not one global
leaderboard:

1. candidate retrieval from in-network and out-of-network sources
2. candidate hydration with metadata
3. filtering for ineligible, seen, muted, old, duplicate, or blocked content
4. multi-action prediction such as favorite, reply, repost, quote, click,
   profile_click, video_view, photo_expand, share, dwell, follow_author,
   not_interested, block_author, mute_author, and report
5. weighted ranking
6. diversity, final selection, and visibility filtering

Important constraint:
- public code and docs do not expose exact production weights
- production systems can change
- this project should produce a heuristic X-fit review, not a fake viral score

## Strong Parts

- Strong because it changes the drafting objective from "pretty tweet" to
  "right audience, right action, low negative feedback".
- Strong because it matches the account strategy: public notebook, concrete
  build logs, markets x systems x ML infra.
- Strong because it can be implemented locally without X write access.
- Strong because it creates durable review files inside each draft folder,
  making later manual posting decisions auditable.

## Risks

- Overfitting to a public approximation of X ranking.
- Turning the tool into engagement bait if scores are misnamed as "viral".
- Scope creep through X API imports, peer analysis, or analytics dashboards.
- Weak local heuristics if repeated-post memory is missing or sync is disabled.
- Recommending media as decoration rather than information.

## Stage 1 MVP

Implement local heuristic review only:

- `tw algo-review <draft_id|latest>`
- `tw media-plan <draft_id|latest>`
- `tw distribution-plan <draft_id|latest>`
- `tw draft --algo-aware ...`

Per draft, write:

- `07_algorithm_review.md`
- `08_media_plan.md`
- `09_distribution_plan.md`

Workspace defaults:

- `profile/x_algorithm_principles.md`
- `profile/x_fit_rubric.yaml`

Tests:

- algo-review creates `07_algorithm_review.md`
- media-plan creates `08_media_plan.md`
- distribution-plan creates `09_distribution_plan.md`
- `--algo-aware` runs all three
- no publish command is called or exposed
- repeated idea is flagged
- crypto / financial-advice wording is flagged
- decorative media is rejected
- thread is rejected when it is one idea stretched over many posts

## Stage 2 Backlog

These ideas are intentionally postponed, not discarded.

### `tw analyze-peer <username_or_url> --limit N`

Read-only peer analysis through configured X read provider or official API.

Why strong:
- can show what formats work in the user's actual audience cluster
- helps adapt topic/format patterns without copying style blindly
- can identify media usage, hooks, reply patterns, and recurring topics

Why postponed:
- needs credentials / provider setup
- more API failure modes and rate limits
- can distract from the local review layer

### `tw analyze-own --sync`

Sync own posted content if read provider is configured, then analyze repetition,
topic drift, and format mix.

Why strong:
- improves repetition detection
- turns the local content machine into an experiment log
- helps avoid posting the same idea too often

Why postponed:
- depends on read-only X sync being configured
- current MVP can still use local posts table and memory

### `tw experiment-log`

Show format history: short, build-log, thread, media, reply, article-note,
question.

Why strong:
- makes account strategy measurable
- helps keep cluster consistency
- prevents repeated weak formats

Why postponed:
- useful after enough drafts/posts exist

Related completed MVP:
- `tw outcome` and `tw outcomes` were added on 2026-06-09 as the manual-first
  outcome layer from the product roadmap.
- This is not the full `tw experiment-log` yet.
- It records high-value interactions per draft and writes
  `20_high_value_interactions.md`.
- It creates the local data needed before format/outcome history becomes useful.

### `tw anti-spam latest`

Dedicated checker for repeated idea, muted-keyword risk, crypto-shill risk,
overposting risk, generic content risk, and engagement bait.

Why strong:
- clean separate safety gate
- can become a pre-post checklist

Why postponed:
- overlaps Stage 1 algorithm review
- better after first heuristic implementation is stable

### X API Read-Only Import

Use official read endpoints for user timelines and own posts if tokens exist.

Why strong:
- legal read path for peer and own analysis
- can enrich local sources table

Why postponed:
- credentials must never be read as content context
- MVP must remain useful without network/API
