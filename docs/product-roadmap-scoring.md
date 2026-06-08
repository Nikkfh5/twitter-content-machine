# Product Roadmap Scoring

Session anchor:
- date: 2026-06-08
- repo: `C:\N\hse\twitter-content-machine`
- source roadmap: `docs/product-roadmap.md`

Scoring scale: 0-100.

Weights:
- User pain solved: 25
- Strategic leverage: 25
- Feasibility now: 20
- Risk reduction: 15
- Learning/data value: 15

## Ranked Ideas

| Rank | Idea | Score | Verdict | Why |
|---:|---|---:|---|---|
| 1 | Repeated-idea lineage/status-aware review | 91 | Strong | Fixes a current false warning, stops iteration from being punished, small scope, high trust gain. |
| 2 | Adaptive format decision artifact | 89 | Strong | Directly improves post quality and removes the need to know `--thread`, `--build-log`, `--article-note`, etc. |
| 3 | `tw` as personal scribe / natural dictation entry | 86 | Strong | Biggest UX unlock; makes the tool feel like Codex for content instead of a flag-heavy CLI. Needs careful design. |
| 4 | Evidence-based risk detector | 84 | Strong | Replaces brittle lexical checks with explainable risk evidence. Important for trust, but should start small. |
| 5 | Manual high-value interaction analytics | 80 | Strong | Creates feedback loop around quality of audience graph, not vanity metrics. Manual-first is feasible now. |
| 6 | Read-only X enrichment for outcomes | 68 | Normal | Useful, but API access and endpoint limits may block automation. Should come after manual outcome model. |
| 7 | RAG/indexed detector | 62 | Interesting but early | Could help compare drafts against known safe/risky examples, but it is overkill until we have evidence schema and labeled cases. |

## Notes On RAG / Indexed Detector

Verdict: normal-to-interesting, not first.

Real edge:
- Could retrieve similar prior risk cases, approved posts, rejected examples, and
  safe technical uses of suspicious terms.
- Could make detector decisions less brittle than keyword lists.
- Could reuse existing SQLite/FTS memory before adding embeddings.

Risk:
- Easy to overengineer.
- Without labeled examples, retrieval can amplify noise.
- It may produce a false sense of intelligence if the final decision still lacks
  evidence.

Best path:
1. Build evidence-based detector first.
2. Store detector cases and outcomes.
3. Add FTS retrieval over detector cases.
4. Only then consider embeddings/RAG if FTS is not enough.

## Implementation Order

1. Fix repeated-idea lineage/status-aware review.
2. Add explicit format decision artifact.
3. Improve personal-scribe UX around `tw "<dictation>"`.
4. Replace risk detector with evidence-based detector.
5. Add manual high-value interaction tracking.
6. Add read-only X outcome enrichment if API allows.
7. Add indexed/RAG risk memory after enough labeled detector cases exist.

## Logging Rule

For non-trivial product work:
- write or update a docs file before/while implementing
- add tests for the behavior
- commit with a focused message
- keep progress in Markdown, not only chat

Superpowers helps structure work, but the durable source of truth in this repo is
Markdown docs plus git commits.
