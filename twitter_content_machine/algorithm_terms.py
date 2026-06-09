from __future__ import annotations


POSITIVE_ACTIONS = [
    "reply",
    "repost/share",
    "dwell",
    "photo_expand",
    "video_view",
    "profile_click",
    "follow_author",
    "click",
]

TOPIC_CLUSTERS = {
    "quant / markets / microstructure": [
        "market",
        "markets",
        "microstructure",
        "backtest",
        "backtesting",
        "fills",
        "fill",
        "fees",
        "latency",
        "execution",
        "hft",
        "orderbook",
        "lob",
        "capacity",
    ],
    "C++ / systems / ML infra": [
        "c++",
        "cpp",
        "systems",
        "infra",
        "latency",
        "compiler",
        "cache",
        "pipeline",
        "ml",
        "model",
        "validation",
        "feature",
    ],
    "build logs / experiments": [
        "build",
        "broke",
        "tried",
        "expected",
        "got",
        "next",
        "experiment",
        "metric",
        "benchmark",
        "protocol",
        "cpd",
    ],
    "learning notes": [
        "misunderstood",
        "learned",
        "realized",
        "changed",
        "wrong",
        "assumption",
        "assumptions",
        "lesson",
        "note",
    ],
}

FINANCE_RISK_TERMS = [
    "buy",
    "sell",
    "long",
    "short",
    "signal",
    "guaranteed return",
    "not financial advice",
]

CRYPTO_SHILL_TERMS = ["alpha", "100x", "easy money", "moon", "gem", "ape"]

ENGAGEMENT_BAIT = ["thoughts?", "agree?", "what do you think?", "like and retweet"]

OVERCLAIM_TERMS = [
    "game changer",
    "revolutionary",
    "changes everything",
    "everyone should",
    "the future of",
    "unlock",
]

MEDIA_TERMS = [
    "chart",
    "plot",
    "graph",
    "diagram",
    "table",
    "screenshot",
    "terminal",
    "cli",
    "output",
    "trace",
    "matrix",
    "diff",
]

STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "in",
    "on",
    "for",
    "with",
    "that",
    "this",
    "it",
    "is",
    "was",
    "i",
    "my",
    "after",
    "before",
    "now",
    "current",
    "guess",
    "small",
    "note",
}
