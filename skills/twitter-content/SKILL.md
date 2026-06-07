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
8. Create a dated draft folder.
9. Produce variants + critique + final candidate.
10. Run X-fit review if algo-aware.
11. Run identity/style review if identity-style is active.
12. Keep all source/context files for debugging.

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

## Commands

- New short draft: `tw draft --short "<idea>"`
- New thread: `tw draft --thread "<idea>"`
- Build log from current repo: `tw draft --build-log "<update>"`
- Refine latest: `tw refine latest --pass human`
- Review latest: `tw review latest`
- List queue: `tw queue`
- Search memory: `tw search "<query>"`
- Algorithm review: `tw algo-review latest`
- Media plan: `tw media-plan latest`
- Distribution plan: `tw distribution-plan latest`
- Algorithm-aware draft: `tw draft --algo-aware --short "<idea>"`
- Import Telegram identity pack: `tw tg-import "<path>" --profile tg_crypto_clean`
- Build style profile: `tw style-build tg_crypto_clean`
- Curate style profile: `tw style-curate tg_crypto_clean`
- Identity-style draft: `tw draft --identity-style tg_crypto_clean --identity-strength 0.35 --short "<idea>"`
- Identity/style review: `tw style-review latest --profile tg_crypto_clean`

If `tw` is unavailable, tell the user to install from the repo with:

```bash
pip install -e .
```

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
