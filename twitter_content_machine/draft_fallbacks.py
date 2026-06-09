from __future__ import annotations


def _variant_short(text: str, tone: str) -> str:
    if tone == "direct":
        return f"I used to hand-wave this: {text}. Current guess: the execution model matters more than the metric I was optimizing."
    if tone == "structured":
        return f"Small note: {text}.\n\nWhat changed for me: a backtest can look clean while the execution assumptions are doing most of the work."
    return f"The uncomfortable part of backtests is not the chart. It is noticing that {text}, and then deciding which assumptions are actually defensible."


def _variant_thread(text: str) -> str:
    return "\n\n".join(
        [
            f"1/ Small build note: {text}.",
            "2/ I used to look first at metrics. Now I first ask what execution assumptions make the result possible.",
            "3/ The annoying part is that a small unrealistic fill rule can dominate a clean-looking strategy report.",
            "4/ Current check: separate model quality from data/execution realism before trusting the output.",
            "5/ Not a conclusion yet. More like a debugging note for future backtests.",
        ]
    )


def generate_variants(text: str, draft_type: str, identity_style_active: bool = False) -> tuple[str, str, str]:
    if draft_type == "adaptive":
        return (
            f"I want to make this project note more than a one-line update:\n\n{text}\n\nThe useful part is the connection between previous project work, benchmark design, and the next thing I want to build.",
            f"Current project note:\n\n{text}\n\nThe thread running through this is benchmark realism. I do not want to claim a result too early; I want to show the setup, the assumptions, and what becomes hard to fake.",
            f"This is the part I want to explain better:\n\n{text}\n\nIt is not just a new topic. It is a continuation of learning how large technical projects fail around protocol, data, baselines, and assumptions.",
        )
    if identity_style_active:
        return (
            f"Clean current-account version:\n\nSmall note from building: {text}.\n\nCurrent guess: the useful part is not the take itself, but which assumption broke.",
            f"Raw/personal version:\n\nI used to think this was simpler: {text}.\n\nNow it feels more annoying. The system breaks around assumptions, not around the pretty metric.",
            f"Compressed X-native version:\n\n{text}.\n\nThe annoying part is that the wrong assumption can look like insight until you test it.",
        )
    if draft_type == "thread":
        a = _variant_thread(text)
        b = _variant_thread(text).replace("Small build note", "Backtest note")
        c = _variant_thread(text).replace("The annoying part", "The fake precision starts")
        return a, b, c
    if draft_type == "article-note":
        base = f"Read this and took one useful question from it: {text}."
        return (
            f"{base}\n\nWhat I want to test: whether the idea survives contact with my own project assumptions.",
            f"{base}\n\nUseful part: it gives me a sharper way to check regimes instead of trusting one average backtest.",
            f"{base}\n\nI do not fully buy the conclusion yet. But the framing is useful enough to test.",
        )
    if draft_type == "build-log":
        return (
            f"Build log: {text}.\n\nWhat broke: the assumption was cleaner than the system. Next check: isolate the failure instead of polishing the explanation.",
            f"Tried: {text}.\n\nChanged my mind on one thing: the boring plumbing can decide whether the result means anything.",
            f"The useful part of today's project work: {text}. Not a big lesson, just a constraint I cannot ignore anymore.",
        )
    if draft_type == "question":
        return (
            f"Question for people who have dealt with this: {text}. Any good references that are practical, not just high-level?",
            f"Looking for resources on this: {text}. Especially interested in failure cases and implementation details.",
            f"Small question: {text}. What is the least hand-wavy thing worth reading/testing here?",
        )
    return (
        _variant_short(text, "direct"),
        _variant_short(text, "structured"),
        _variant_short(text, "sharp"),
    )
