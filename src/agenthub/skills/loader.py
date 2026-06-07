from __future__ import annotations

from pathlib import Path


DEFAULT_AGENT_SKILLS = {
    "ui_builder": ["skills/ui_builder.md"],
    "code_reviewer": ["skills/code_review.md"],
}

DEFAULT_TOOL_SKILLS = {
    "preview_tool": ["skills/preview.md"],
}


def load_skill(path: str | Path) -> str:
    skill_path = Path(path)
    if not skill_path.exists():
        return ""
    return skill_path.read_text(encoding="utf-8")


def load_skills_for_agent(agent_id: str, paths: list[str] | None = None) -> list[str]:
    skill_paths = paths if paths is not None else DEFAULT_AGENT_SKILLS.get(agent_id, [])
    return [text for text in (load_skill(path) for path in skill_paths) if text.strip()]


def load_skills_for_tool(tool_id: str, paths: list[str] | None = None) -> list[str]:
    skill_paths = paths if paths is not None else DEFAULT_TOOL_SKILLS.get(tool_id, [])
    return [text for text in (load_skill(path) for path in skill_paths) if text.strip()]

