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
7. Create a dated draft folder.
8. Produce variants + critique + final candidate.
9. Keep all source/context files for debugging.

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

Never:
- publish to X
- call any write/post API
- leak private details
- create files in the current project unless explicitly asked

## Commands

- New short draft: `tw draft --short "<idea>"`
- New thread: `tw draft --thread "<idea>"`
- Build log from current repo: `tw draft --build-log "<update>"`
- Refine latest: `tw refine latest --pass human`
- Review latest: `tw review latest`
- List queue: `tw queue`
- Search memory: `tw search "<query>"`

If `tw` is unavailable, tell the user to install from the repo with:

```bash
pip install -e .
```
