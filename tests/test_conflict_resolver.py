from agenthub_harness.artifacts.conflict_resolver import resolve_artifact_conflicts


def test_conflict_resolver_dedupes_artifact_ids() -> None:
    artifacts, conflicts = resolve_artifact_conflicts(
        [
            {"id": "art_001", "type": "code", "title": "A", "content": "one"},
            {"id": "art_001", "type": "code", "title": "B", "content": "two"},
        ]
    )

    assert [artifact["id"] for artifact in artifacts] == ["art_001", "art_001_2"]
    assert conflicts == []


def test_conflict_resolver_emits_file_path_conflict_artifact() -> None:
    artifacts, conflicts = resolve_artifact_conflicts(
        [
            {
                "id": "a",
                "type": "code",
                "title": "TodoList.tsx",
                "file_path": "TodoList.tsx",
                "content": "one",
                "producer_agent_id": "ui_builder",
            },
            {
                "id": "b",
                "type": "code",
                "title": "TodoList.tsx",
                "file_path": "TodoList.tsx",
                "content": "two",
                "producer_agent_id": "code_reviewer",
            },
        ]
    )

    assert conflicts[0].target == "TodoList.tsx"
    assert artifacts[-1]["type"] == "conflict"
