# Product Roadmap Progress

Session anchor:
- date: 2026-06-08
- roadmap: `docs/product-roadmap.md`
- scoring: `docs/product-roadmap-scoring.md`

## Completed In This Pass

### 1. Scored roadmap

Created a 100-point prioritization rubric in `docs/product-roadmap-scoring.md`.

Scoring dimensions:
- user pain solved
- strategic leverage
- feasibility now
- risk reduction
- learning/data value

Top implementation order:
1. repeated-idea lineage/status-aware review
2. adaptive format decision artifact
3. `tw` as personal scribe / natural dictation entry
4. evidence-based risk detector
5. manual high-value interaction analytics
6. read-only X enrichment
7. RAG/indexed detector

### 2. Repeated-idea review fix

Changed algorithm-aware review so repetition risk is based on already committed
publication intent, not rough working memory.

Now ignored for repeated-post risk:
- captured ideas
- ordinary `draft` drafts
- intermediate failed drafts

Still counted for repeated-post risk:
- `ready` drafts
- `posted` drafts
- imported/synced own posts

Reason:
- iteration should not be punished as spam
- only ready/posted material represents real audience repetition risk

## Verification

Focused tests:
- idea memory does not trigger repeated-post risk
- plain draft memory does not trigger repeated-post risk
- ready draft memory does trigger repeated-post risk
- crypto/financial-advice risk still rejects unsafe wording
- normal technical words still avoid crypto substring false positives

Full test suite:
- `51 passed`

Manual smoke:
- `tw algo` on active coursework/FNL draft
- repeated idea risk became low
- decision became `publish candidate`

## Next Planned Item

Implement the adaptive format decision artifact.

Target artifact:
- `FORMAT_DECISION.md` or numbered draft artifact

It should record:
- target audience
- content density
- best format
- why other formats were not chosen
- expected primary action
- target length range

