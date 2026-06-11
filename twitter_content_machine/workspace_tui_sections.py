from __future__ import annotations


SCREEN_HEADINGS = [
    "Draft preview",
    "Summary",
    "Problems",
    "Decisions",
    "Progress",
    "Files",
    "Recent activity",
]


def split_screen(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {"state": []}
    current = "state"
    for line in text.splitlines():
        if line in SCREEN_HEADINGS:
            current = line
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    result = {key: "\n".join(value).strip() for key, value in sections.items()}
    state_lines = result.get("state", "").splitlines()
    next_lines = [line for line in state_lines if line.startswith("Next action:")]
    result["state"] = "\n".join(line for line in state_lines if not line.startswith("Next action:")).strip()
    result["next"] = next_lines[0].replace("Next action:", "").strip() if next_lines else "/draft <idea>"
    for heading in SCREEN_HEADINGS:
        result.setdefault(heading, "")
    result["progress"] = result.get("Progress", "")
    return result
