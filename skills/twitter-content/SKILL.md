---
name: twitter-content
description: Use when the user wants to turn a raw idea, article, project update, repo context, or learning note into a draft X/Twitter post or thread in Nikita's public-notebook style. This skill creates drafts only and never publishes.
---

# Twitter Content Skill

Use this skill to create or refine draft posts.

Default behavior:
1. Do not publish.
2. Use the local `tw` CLI if available.
3. Run `tw ensure`.
4. Detect current project.
5. Refresh project context centrally.
6. Search memory for related old drafts/posts.
7. If identity/style is configured, use it at safe strength <= 0.35 unless user asks otherwise.
8. Create a dated draft folder with `13_context_bundle.md/json` and `14_llm_request.md`.
9. Prefer plain `tw draft "<idea>"`; it uses Codex CLI, X-fit review, and `tg_crypto_clean` automatically when the profile exists.
10. Treat the newest draft as the active draft; prefer `tw show`, `tw edit`, `tw review`, and `tw algo` without `latest` unless a specific older draft is needed.
11. For already prepared notes/articles, use `tw codex --prepare --file <file> --thread` to create a native content Codex session instead of running Codex in the repo root.
12. Produce variants + critique + final candidate through the CLI.
13. Run X-fit review if algo-aware.
14. Run identity/style review if identity-style is active.
15. Keep all source/context files for debugging.

For graph bootstrap work, use the CLI as a strategy/operator layer. The
bootstrap agent creates manual queues, digests, quote candidates, and daily
actions. It does not perform social actions.

If the user did not specify format, ask or infer one of:
- short
- thread
- article-note
- build-log
- question

Always check:
- real point
- repetition
- overclaiming
- confidentiality
- financial-advice risk
- GPT-like phrasing
- X-fit: audience cluster, predicted action, negative feedback risk, format/media fit

Never:
- publish to X
- call any write/post API
- leak private details
- create files in the current project unless explicitly asked
- imitate forwarded Telegram posts as the user's style
- manually write a tweet if the CLI can create a draft
- auto-follow, auto-like, auto-reply, auto-quote, auto-repost, or auto-publish
- turn `follow-seed` into an X follow action
- make replies mandatory in low_social bootstrap mode

## Commands

- New default draft: `tw draft "<idea>"`
- New short draft: `tw draft --short "<idea>"`
- Local fallback draft: `tw draft --no-llm "<idea>"`
- Context-only request: `tw draft --context-only --print-prompt-path "<idea>"`
- New thread: `tw draft --thread "<idea>"`
- Build log from current repo: `tw draft --build-log "<update>"`
- Show active draft: `tw show`
- Edit active draft through Codex CLI: `tw edit "<instruction>"`
- Refine active draft: `tw refine --pass human`
- Review active draft: `tw review`
- List drafts: `tw drafts`
- Switch active draft: `tw use 2`
- Search memory: `tw search "<query>"`
- Smart search through Codex CLI: `tw search --smart "<query>"`
- Import style/content gold references: `tw style-gold-import "<zip-or-folder>"`
- Prepare native Codex content session: `tw codex --prepare`
- Prepare session from file: `tw codex --prepare --file "<notes.md>" --thread`
- Run Codex in prepared session: `tw codex --run`
- Algorithm review layers: `tw algo`
- Algorithm review: `tw algo-review`
- Media plan: `tw media-plan`
- Distribution plan: `tw distribution-plan`
- Disable X-fit review once: `tw draft --no-algo-aware "<idea>"`
- Import Telegram identity pack: `tw tg-import "<path>" --profile tg_crypto_clean`
- Build style profile: `tw style-build tg_crypto_clean --auto`
- Refresh style profile: `tw style-refresh tg_crypto_clean`
- Style stats: `tw style-stats tg_crypto_clean`
- Curate style profile: `tw style-curate tg_crypto_clean`
- Identity-style draft: `tw draft --identity-style tg_crypto_clean --identity-strength 0.35 "<idea>"`
- Identity/style review: `tw style-review --profile tg_crypto_clean`
- Sync own X posts read-only: `tw sync-posted`
- Analyze own posts: `tw analyze-own --sync`
- Import peer posts read-only: `tw x-read @handle --limit 100`
- Analyze peer posts: `tw analyze-peer @handle --limit 100`
- Create 14-day bootstrap plan: `tw bootstrap --days 14`
- Static plan command alias: `tw bootstrap-plan --days 14`
- Create today's daily operator packet: `tw today --refresh`
- Create today's packet with live read-only X scan: `tw today --refresh --live-x`
- Show today's stored bootstrap actions: `tw today`
- Add target account: `tw target-accounts add @handle --cluster quant --note "..."`
- Import target accounts: `tw target-accounts import accounts.csv --cluster quant`
- Build manual follow queue: `tw follow-seed --cluster quant --limit 30`
- Run read-only graph scan: `tw graph-scan --cluster quant --limit 30 --posts 50`
- Create Russian digest from cached/read-only sources: `tw x-digest --cluster quant --limit 50 --ru`
- Show quote candidates: `tw quote-candidates latest`
- Draft from digest: `tw draft-from-digest latest --short`
- Review graph state: `tw graph-review`
- Weekly bootstrap review: `tw weekly-review`

If `tw` is unavailable, tell the user to install from the repo with:

```bash
pip install -e .
```

## Context Bundle / Isolated Generation

`tw draft` can be run from any project folder, but content generation must use
the generated draft folder as the active context.

Expected generated files:
- `13_context_bundle.md`
- `13_context_bundle.json`
- `14_llm_request.md`
- `16_llm_parse_report.md`
- `AGENTS.override.md`
- `.codex_home/AGENTS.md`
- active draft pointer: `~/twitter-system/state/current_draft.txt`
- edit artifacts: `17_edit_request.md`, `18_edit_raw_output.md`, `19_edit_parse_report.md`, and `revisions/*.md`
- bootstrap distribution artifact: `17_distribution_bootstrap.md`
- graph bootstrap folders: `~/twitter-system/graph/plans/`,
  `~/twitter-system/graph/follow_queue/`, `~/twitter-system/graph/digests/`,
  and `~/twitter-system/graph/scans/`
- native content session folder: `~/twitter-system/codex_sessions/<session_id>/`
- content session files: `AGENTS.md`, `TASK.md`, `INPUT.md`, `CONTEXT_BUNDLE.md`, `OUTPUT_SCHEMA.md`, `output/`, `.codex_home/AGENTS.md`

Rules:
- Source project `AGENTS.md` may be summarized into the context bundle.
- Source project `AGENTS.md` must not become active instructions for content generation.
- Draft folder `AGENTS.override.md` is the content-generation instruction layer.
- For manual/final text work, never run Codex directly from the repo root.
  Prepare a content session with `tw codex --prepare` and run Codex from that
  session folder.
- Default configurable model is `gpt-5.5` with `reasoning_effort=xhigh` and `speed=fast`.
- Normal `tw draft` requires Codex CLI. If Codex is missing or returns invalid output, report the failure in `16_llm_parse_report.md` and fail the command.
- Use `--no-llm` only when the user explicitly wants a local fallback draft.

## X Algorithm-Aware Drafting

Do not optimize for generic virality. Optimize for personalized recommendation
fit.

Treat the X For You feed as:
1. candidate retrieval
2. candidate hydration
3. filtering
4. multi-action prediction
5. weighted ranking
6. author diversity / final selection

For each draft, decide:

- target audience cluster
- candidate retrieval fit
- primary predicted action
- secondary predicted action
- negative action risk
- media fit
- thread vs short-post decision
- repetition risk versus previous posts

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

Rules:
- Do not write generic engagement bait.
- Do not write fake contrarian takes.
- Do not produce financial advice or crypto shilling.
- Prefer concrete observations from projects.
- Prefer uncertainty when true.
- Prefer a single strong idea over a long generic thread.
- Suggest media only when it adds information: chart, diagram, terminal screenshot, plot, table.
- First post of a thread must be independently valuable.
- Avoid posting many variants of the same idea.
- Keep the account focused on markets / systems / ML infra / build logs.

## Identity Style

Use `identity_style`, not "voice".

Default profile:
- `tg_crypto_clean`

Default safe strength:
- `0.35`

Use sources:
- own original Telegram messages
- own self-forwarded messages
- curated gold examples
- style card
- anti-pattern rules

Do not use by default:
- `forwarded_other`
- `private`
- `reject`
- wallet/address-only messages
- airdrop instructions
- referral/shill posts

When identity-style is active, draft folder should include:
- `10_identity_style_review.md`
- `11_examples_used.md`
- `12_risk_flags.md`

Keep:
- directness
- rough rhythm
- skepticism
- bet/risk thinking
- concrete mechanics

Remove:
- crypto shilling
- direct token/price calls
- FOMO
- guru certainty
- financial advice
