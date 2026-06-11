from __future__ import annotations

import argparse

from ..outcomes import format_outcome_rows, list_outcomes, record_outcome
from ..state import resolve_active_draft_id, set_current_draft


def _cmd_outcome(args: argparse.Namespace) -> int:
    draft_id = resolve_active_draft_id(getattr(args, "draft_id", None))
    result = record_outcome(
        draft_id=draft_id,
        handle=args.handle,
        action=args.action,
        why_important=args.why,
        audience_cluster=args.cluster or "",
        relationship=args.relationship or "",
        quality_note=args.quality_note or "",
        follow_up_needed=bool(args.follow_up),
    )
    set_current_draft(draft_id)
    print(f"recorded outcome: {result.id}")
    print(result.artifact_path)
    return 0


def _cmd_outcomes(args: argparse.Namespace) -> int:
    draft_id = None if args.all else resolve_active_draft_id(getattr(args, "draft_id", None))
    print(format_outcome_rows(list_outcomes(draft_id=draft_id, limit=args.limit)))
    return 0
