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
    "x_algorithm_principles.md": """# X Algorithm Principles

Optimize for personalized recommendation fit, not generic virality.

A draft should pass four checks:

1. Candidate retrieval fit
   - clear audience cluster
   - connected to markets / systems / ML infra / build logs
   - consistent with previous account direction

2. Positive action prediction
   - choose 1-2 likely actions: reply, repost/share, dwell, photo_expand,
     profile_click, follow_author, click

3. Negative action risk
   - avoid not_interested, block_author, mute_author, report
   - avoid spammy crypto/finance wording, overclaiming, repeated ideas,
     generic motivational content, and engagement bait

4. Format fit
   - short post for one idea
   - thread only when each part adds independent value
   - media only when it increases understanding
   - question only when bounded and non-bait
""",
    "x_fit_rubric.yaml": """x_fit_rubric:
  candidate_retrieval_fit:
    description: "Clear topic/audience cluster; likely similar to viewers' engagement history"
  concrete_value:
    description: "Specific observation, example, failure, metric, or useful framing"
  positive_action_potential:
    description: "Likely to trigger reply/repost/dwell/profile_click/follow/photo_expand"
  negative_feedback_safety:
    description: "Low risk of not_interested/mute/block/report"
  style_authenticity:
    description: "Sounds like Nikita's public notebook, not GPT/LinkedIn/influencer"
  media_fit:
    description: "Media increases understanding or engagement"
decision_rule:
  publish_candidate: "total >= 22 and no high safety risk"
  revise: "total 16-21 or fixable medium risk"
  reject: "total < 16 or high safety risk"
""",
    "graph_bootstrap_agent.md": """# Graph Bootstrap Agent

Mission:
Build the first relevant social graph for a cold X account without spam, mass automation, or heavy social interaction.

The agent optimizes for:
- high-quality follows
- clear topic clusters
- useful digests
- standalone/quote-note opportunities
- profile conversion
- long-term trust

The agent does not optimize for:
- generic virality
- aggressive follow/unfollow
- mass replies
- automated likes
- bot-like activity
- financial advice
- crypto shilling

Default mode:
low_social cold_start

Human actions required:
- manually follow selected accounts
- manually publish posts
- manually choose quote notes
""",
}

PROFILE_CLUSTER_FILES = {
    "quant.md": """# quant

Target:
- market microstructure
- backtesting realism
- execution assumptions
- quant dev
- HFT/systematic trading

Avoid:
- trading signals
- alpha promises
- crypto shilling
- guru PnL tone
""",
    "systems.md": """# systems

Target:
- C++
- systems design
- low latency
- infrastructure
- performance debugging
""",
    "ml_infra.md": """# ml_infra

Target:
- recommender systems
- feature stores
- data pipelines
- model serving
- ML systems
""",
    "ai_agents.md": """# ai_agents

Target:
- Codex
- developer tooling
- local agents
- MCP
- content/workflow automation
""",
    "builders.md": """# builders

Target:
- technical public notebooks
- students building projects
- small tools
- honest progress logs
""",
}

WORKSPACE_DIRS = [
    "profile",
    "identity_styles",
    "inbox/raw",
    "drafts",
    "ready",
    "posted",
    "rejected",
    "projects",
    "state",
    "sources/articles",
    "sources/x_posts",
    "sources/telegram",
    "sources/notes",
    "searches",
    "sessions",
    "codex_sessions",
    "db",
    "graph/target_accounts",
    "graph/follow_queue",
    "graph/digests",
    "graph/plans",
    "graph/scans",
    "graph/reports",
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
    clusters_dir = root / "profile" / "clusters"
    clusters_dir.mkdir(parents=True, exist_ok=True)
    for name, content in PROFILE_CLUSTER_FILES.items():
        path = clusters_dir / name
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
