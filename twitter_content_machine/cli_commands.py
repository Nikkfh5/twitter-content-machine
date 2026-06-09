from __future__ import annotations

from .commands.core import (
    _cmd_capture,
    _cmd_doctor,
    _cmd_drafts,
    _cmd_ensure,
    _cmd_idea,
    _cmd_init,
    _cmd_mark,
    _cmd_mcp,
    _cmd_open,
    _cmd_path,
    _cmd_queue,
    _cmd_refresh_context,
    _cmd_show,
    _cmd_use,
    list_drafts,
    save_idea,
)
from .commands.draft_ops import (
    _cmd_algo,
    _cmd_algo_review,
    _cmd_codex,
    _cmd_distribution_plan,
    _cmd_draft,
    _cmd_edit,
    _cmd_media_plan,
    _cmd_refine,
    _cmd_review,
)
from .commands.io_ops import (
    _cmd_analyze_own,
    _cmd_analyze_peer,
    _cmd_article,
    _cmd_search,
    _cmd_sync_posted,
    _cmd_x_read,
)
from .commands.style_ops import (
    DEFAULT_IDENTITY_PROFILE,
    _cmd_style_build,
    _cmd_style_curate,
    _cmd_style_gold_import,
    _cmd_style_learn,
    _cmd_style_refresh,
    _cmd_style_review,
    _cmd_style_stats,
    _cmd_tg_import,
)

__all__ = [name for name in globals() if name.startswith("_cmd_")] + [
    "DEFAULT_IDENTITY_PROFILE",
    "list_drafts",
    "save_idea",
]
