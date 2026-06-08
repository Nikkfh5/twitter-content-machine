# Content Machine Product Roadmap

Session anchor:
- date: 2026-06-08
- repo: `C:\N\hse\twitter-content-machine`
- purpose: durable backlog for the user's higher-level product direction

This file is the top-level roadmap for future work. It should be read before
project-advisor passes, larger refactors, or any new "what should we build next"
discussion. More focused backlogs can still live in feature-specific docs, but
they should link back here.

## Product Direction

The tool should stop feeling like a pile of CLI flags and become a personal
content operator:

```text
user dictates raw intent
  -> tool gathers project/context/style/audience signals
  -> Codex chooses format and structure
  -> draft folder becomes the editing workspace
  -> user iterates through Codex/native files
  -> outcomes are tracked and used for future decisions
```

The user should be able to speak naturally:

```text
I want to write about this project.
Here is why it matters.
Here is who it is for.
Look at these files/context if needed.
Make it sound like my public notebook, not LinkedIn.
Choose whether it should be a post, thread, build log, or article note.
```

The system should decide the mechanics, not ask the user to remember flags.

## Priority 1: Finish The Current Post Quality Loop

Current state:
- The coursework/FNL/options post was rewritten into a stronger adaptive post.
- `tw review` considers it usable.
- `tw algo` no longer falsely flags finance/crypto risk after the substring
  detector fix.
- It can still mark repeated-idea risk when a failed earlier draft contains the
  same raw idea.

Next work:
- Make repeated-idea detection aware of draft lineage and failed/intermediate
  drafts.
- A rewritten revision of the same active draft should not be treated as a new
  spammy repetition.
- Repeated-idea warnings should distinguish:
  - same active draft / revision history
  - previous rejected draft
  - previous ready/posted text
  - unrelated memory match

Why this is strong:
- It stops useful iteration from being punished.
- It makes review output more trustworthy.
- It supports the user's real workflow: draft, edit, improve, then review again.

## Priority 2: Smarter Risk Detector

Problem:
- The current detector is too lexical.
- It previously matched `ape` inside `shape`.
- Similar shallow checks can still produce false positives or miss context.
- We should not keep adding one-off word patches.

Target behavior:
- Risk detection should be context-aware and explainable.
- It should flag real financial advice, crypto shilling, fake certainty, and
  engagement bait.
- It should not punish normal technical language like benchmark, shape,
  submission, model outputs, options research, or paper/article wording.

Suggested design:
- Keep a fast rule layer for obvious hard rejects:
  - `100x`
  - `easy money`
  - explicit buy/sell recommendations
  - "not financial advice" used as a shield
  - referral/airdrop/shill patterns
- Use token/phrase boundaries for lexical checks, never raw substring matching.
- Add contextual allow rules for technical uses:
  - options as an instrument/project domain, not advice
  - benchmark / baselines / validation / model outputs
  - paper, submission, article, coursework
- Add a model-assisted review layer for ambiguous cases:
  - input: final candidate + risk categories + account rules
  - output: category, severity, quoted trigger, reason, suggested edit
  - never autopublish
- Store detector evidence in review artifacts:
  - `matched_term`
  - `match_context`
  - `risk_category`
  - `confidence`
  - `reason`

Acceptance criteria:
- No substring false positives.
- Finance/crypto warnings include exact evidence.
- Ambiguous technical posts do not become `reject` without a concrete reason.
- Real shill/advice wording remains rejected.

## Priority 3: Adaptive Format Selection

Problem:
- The old default behaved like `short`, which compressed good ideas into boring
  posts.
- The user has Premium and is not constrained to tiny 280-character posts.
- A good idea should become a fuller post when it has enough substance.

Current state:
- `tw draft "..."` now defaults to `adaptive`.
- `--short` remains available when the user explicitly wants compact output.

Target behavior:
- The model should choose the best narrative form:
  - adaptive single post
  - short post
  - thread
  - build log
  - article note
  - question
  - reply/quote draft
  - media-supported post
- The user should not need to know the flag in advance.
- The output should include a format decision with reasoning.

Suggested design:
- Add a `format_decision` artifact before generation:
  - `target_audience`
  - `content_density`
  - `best_format`
  - `why_not_other_formats`
  - `expected_primary_action`
  - `length_range`
- If the content has a process, experiment, or multi-step argument, consider a
  thread.
- If it is a project update with what changed/broke/next step, use build log.
- If it reacts to a paper/article/source, use article note.
- If it asks for technical input, use bounded question.
- If it has one compact observation, use short post.
- If it has rich context but not enough independent parts for a thread, use
  adaptive single post with 2-5 short paragraphs.

Why this is strong:
- It preserves good ideas instead of compressing them.
- It turns dictation into a format-aware writing workflow.
- It avoids both extremes: one-line boredom and fake stretched threads.

## Priority 4: `tw` As Personal Scribe

Problem:
- The current CLI still feels like a technical utility.
- The user does not want to remember flags, draft IDs, or command variants.
- The desired workflow is closer to Codex: natural instruction, visible
  workspace, iterative editing.

Target daily UX:

```powershell
tw "raw dictated instruction / idea / context"
```

The command should:
- treat the text as an instruction bundle, not only raw tweet content
- infer whether the user is giving:
  - core idea
  - style preference
  - audience
  - importance
  - files/context to inspect
  - desired format
  - constraints
- create or update the active draft
- run Codex with the right local AGENTS/context
- leave the user in a useful draft folder workflow

Possible command surfaces:
- `tw "<dictated instruction>"`: primary daily entry
- `tw edit "<instruction>"`: edit active draft
- `tw session`: prepare/open Codex-native draft session
- `tw status`: show active draft, latest candidate, review state, next actions
- `tw accept`: mark current candidate ready
- `tw reject`: reject current active draft

Important design rule:
- Keep advanced flags for debugging, but hide them from daily flow.
- The user should not need `--llm`, `--model`, `--algo-aware`, `--identity-style`,
  or draft IDs in ordinary use.

Draft folder should become the native working unit:
- `TASK.md`
- `INPUT.md`
- `CONTEXT_BUNDLE.md`
- `FORMAT_DECISION.md`
- `VARIANTS.md`
- `FINAL.md`
- `REVIEWS.md`
- `NEXT_ACTIONS.md`

Why this is strong:
- It matches how the user actually dictates ideas.
- It makes the CLI feel like a writing partner, not a command parser.
- It lets Codex handle mechanics while keeping everything inspectable on disk.

## Priority 5: High-Value Interaction Analytics

Problem:
- Raw views/likes are not enough.
- A good reply/repost/follow from a high-quality relevant account can matter
  more than many low-quality impressions.
- The user wants to learn which posts attract the right graph, not just more
  traffic.

Concepts to track per post:
- `high_value_interactions`
- `handle`
- `why_important`
- `action`
  - follow
  - reply
  - repost
  - quote
  - profile click if available
- `audience_cluster`
  - quant
  - systems
  - ML infra
  - markets
  - research
  - HSE/CS
- `relationship`
  - peer
  - strong account
  - researcher
  - builder
  - potential collaborator
  - unknown
- `quality_note`
- `follow_up_needed`

Possible implementation stages:

1. Manual-first
   - After posting manually, user can add outcome notes:
     `tw outcome latest --handle @x --action reply --why "quant dev with relevant benchmark work"`
   - Store in SQLite and Markdown.
   - This is immediately useful and does not depend on X API limits.

2. Read-only sync
   - Use X read-only endpoints where available.
   - Import public metrics and visible interactions.
   - Do not use write APIs.
   - Treat API gaps honestly; some high-value signals may require manual notes.

3. Account memory
   - Maintain local `accounts` table:
     - handle
     - display name
     - cluster
     - why important
     - first seen
     - last interaction
     - notes
   - Let future reviews know when a post attracted the right people.

4. Post learning loop
   - Compare formats and topics by quality-weighted outcomes:
     - which posts got useful replies
     - which posts got relevant reposts
     - which posts caused follows from the target cluster
     - which posts only got generic engagement
   - Feed this into future `format_decision` and `algorithm_review`.

Why this is strong:
- It aligns growth with the right graph, not vanity metrics.
- It creates feedback for the content machine.
- It helps the user develop a public notebook around serious technical work.

Open questions:
- Which X API tier exposes enough interaction detail?
- How much should remain manual because high-value interaction quality is
  subjective?
- Should handle quality be user-labeled, model-suggested, or both?

## Suggested Build Order

1. Fix repeated-idea lineage in algorithm review.
2. Replace shallow risk detector with evidence-based detector.
3. Add explicit `format_decision` artifact and improve adaptive format choice.
4. Design `tw "<dictation>"` personal-scribe UX.
5. Add manual high-value interaction tracking.
6. Add read-only X enrichment where API access allows.
7. Feed outcome analytics back into draft review and format selection.

## Non-Negotiables

- Draft-only by default.
- Never autopublish.
- Never call X write APIs.
- Keep all decisions inspectable in Markdown/SQLite.
- Prefer natural daily UX over exposing flags.
- Do not paper over bad detectors with one-off text hacks; improve the detector
  design and store evidence.
- Do not optimize for generic virality.
- Optimize for the right audience graph and useful technical reputation.
