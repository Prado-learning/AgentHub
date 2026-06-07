from __future__ import annotations

from agenthub.skills.loader import load_skill


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, str] = {}

    def register(self, skill_id: str, path: str) -> None:
        self._skills[skill_id] = load_skill(path)

    def get(self, skill_id: str) -> str:
        return self._skills.get(skill_id, "")

    def list_ids(self) -> list[str]:
        return list(self._skills)

