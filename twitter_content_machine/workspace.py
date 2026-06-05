from __future__ import annotations

from pathlib import Path

from .config import DEFAULT_CONFIG, default_root
from .db import migrate
from .models import Workspace


PROFILE_FILES = {
    "persona.md": """This account is a public notebook for a CS student/engineer moving through C++/ML infrastructure, markets, quant systems, and project building.

The account should not pretend to be an expert. It should show progress, mistakes, checks, and changes in understanding.

Core themes:
- CS / HSE / technical learning
- C++ / systems / ML infrastructure
- markets / quant / market microstructure
- build logs
- article notes
- backtesting and data realism
- mistakes and false assumptions
""",
    "style.md": """Style:
- direct
- specific
- slightly rough is okay
- no influencer tone
- no corporate tone
- no fake expertise
- no fake contrarianism
- no motivational ending
- no long generic introductions
- prefer concrete details
- prefer uncertainty when true
- write as a public working notebook
""",
    "forbidden_phrases.md": """Avoid:
- in today's world
- important to note
- it is worth mentioning
- this highlights
- this underscores
- game changer
- unlock
- deep dive
- leverage
- cutting-edge
- revolutionary
- here are 5 lessons
- everyone should
- the future of
- I am excited to announce
""",
    "topics.md": """Topics:
- CS / HSE / technical learning
- C++ / systems / ML infrastructure
- markets / quant / market microstructure
- build logs
- article notes
- backtesting and data realism
- mistakes and false assumptions
""",
    "safety.md": """Never:
- publish automatically
- produce trading signals
- give financial advice
- leak company/internal/private data
- expose secrets
- mention private details from repos
- overstate achievements
- imply official company position
""",
}

WORKSPACE_DIRS = [
    "profile",
    "inbox/raw",
    "drafts",
    "ready",
    "posted",
    "rejected",
    "projects",
    "sources/articles",
    "sources/x_posts",
    "sources/notes",
    "db",
    "logs",
]


def ensure_workspace(root: Path | None = None) -> Workspace:
    root = (root or default_root()).expanduser().resolve()
    for rel in WORKSPACE_DIRS:
        (root / rel).mkdir(parents=True, exist_ok=True)
    config_path = root / "config.toml"
    if not config_path.exists():
        config_path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    for name, content in PROFILE_FILES.items():
        path = root / "profile" / name
        if not path.exists():
            path.write_text(content, encoding="utf-8")
    ideas_path = root / "inbox" / "ideas.md"
    if not ideas_path.exists():
        ideas_path.write_text("# Ideas\n\n", encoding="utf-8")
    articles_path = root / "inbox" / "articles.md"
    if not articles_path.exists():
        articles_path.write_text("# Articles\n\n", encoding="utf-8")
    db_file = root / "db" / "content.sqlite"
    migrate(db_file)
    return Workspace(root=root, db_path=db_file)


def read_profile(root: Path | None = None) -> dict[str, str]:
    workspace = ensure_workspace(root)
    profile: dict[str, str] = {}
    for path in (workspace.root / "profile").glob("*.md"):
        profile[path.stem] = path.read_text(encoding="utf-8", errors="replace")
    return profile
