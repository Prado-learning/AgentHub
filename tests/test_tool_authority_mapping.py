"""P0-1 — every tool that ships in the default registry must have an
explicit entry in :data:`_TOOL_AUTHORITY`. The default-fallback tier is
useful as a safety net, but it must not be the source of truth — every
write / deploy / external-action tool has to be classified by a human
before it can run in production.

The mapping carries two flavours of tools:

* **shipped** — registered by :func:`build_default_tool_registry`. Must
  be classified and present in :data:`_TOOL_AUTHORITY`.
* **forward-declared** — tools we plan to ship at a known tier. They
  keep their entry so when the implementation lands the tier is
  already decided.

This test loads the real registry (no fakes), then asserts three
properties:

1. Coverage — every shipped tool id is in the mapping.
2. Sanity — the tier assigned to a shipped tool matches the
   classification the test treats as authoritative (allowlists).
3. Forward declarations — forward-declared entries are also in the
   mapping so a future implementation lands at the right tier without
   re-litigating.
"""

from __future__ import annotations

from agenthub.domain.authority import AuthorityTier
from agenthub.orchestration.rule_planner import _TOOL_AUTHORITY, infer_authority
from agenthub.tools.executor import build_default_tool_registry


# Tools that are explicitly designed to be read-only / query / recognise.
# If you add a new tool here, document *why* it can never write.
# Proposal tools only return artifacts. Apply and deploy are separate reviewed actions.
_SHIPPED_L1 = frozenset(
    {
        "file_reader_tool",
        "image_reader_tool",
        "document_preview_tool",
        "code_review_tool",
        "preview_tool",
        "ui_builder_tool",
        "workflow_builder_tool",
    }
)
_SHIPPED_L2 = frozenset()
_SHIPPED_L3 = frozenset({"deploy_tool"})

# Forward declarations: tools the mapping already classifies but whose
# implementation has not landed yet. They get the right tier from day
# one instead of inheriting the (overly permissive) L1 default.
_FORWARD_DECLARED_L2: frozenset[str] = frozenset(
    {
        "file_writer_tool",
        "reply_template_tool",
        "create_artifact_tool",
    }
)

_FORWARD_DECLARED_L3: frozenset[str] = frozenset(
    {
        "push_branch_tool",
        "merge_request_tool",
        "release_tool",
    }
)


def test_every_registered_tool_has_authority_mapping() -> None:
    """Coverage: every tool id in the default registry appears in
    :data:`_TOOL_AUTHORITY`."""

    registered = set(build_default_tool_registry().list_ids())
    mapped = set(_TOOL_AUTHORITY.keys())

    missing = registered - mapped
    assert not missing, (
        f"Tools without authority mapping: {sorted(missing)}. "
        f"Add them to agenthub.orchestration.rule_planner._TOOL_AUTHORITY "
        f"before they ship. Defaulting to L1 silently is a security hole."
    )


def test_registered_l1_tools_match_allowlist() -> None:
    """No shipped read-only tool has been silently reclassified."""

    shipped = set(build_default_tool_registry().list_ids())
    mapped_l1 = {
        tool
        for tool, tier in _TOOL_AUTHORITY.items()
        if tier is AuthorityTier.L1_READONLY and tool in shipped
    }
    assert mapped_l1 == _SHIPPED_L1, (
        f"L1 set drift. mapped (shipped only)={sorted(mapped_l1)} "
        f"allowlist={sorted(_SHIPPED_L1)}"
    )


def test_registered_l2_tools_match_allowlist() -> None:
    shipped = set(build_default_tool_registry().list_ids())
    mapped_l2 = {
        tool
        for tool, tier in _TOOL_AUTHORITY.items()
        if tier is AuthorityTier.L2_REVERSIBLE and tool in shipped
    }
    assert mapped_l2 == _SHIPPED_L2, (
        f"L2 set drift. mapped (shipped only)={sorted(mapped_l2)} "
        f"allowlist={sorted(_SHIPPED_L2)}"
    )


def test_registered_l3_tools_match_allowlist() -> None:
    shipped = set(build_default_tool_registry().list_ids())
    mapped_l3 = {
        tool
        for tool, tier in _TOOL_AUTHORITY.items()
        if tier is AuthorityTier.L3_IRREVERSIBLE and tool in shipped
    }
    assert mapped_l3 == _SHIPPED_L3, (
        f"L3 set drift. mapped (shipped only)={sorted(mapped_l3)} "
        f"allowlist={sorted(_SHIPPED_L3)}"
    )


def test_forward_declared_l2_tools_present_in_mapping() -> None:
    for tool_id in _FORWARD_DECLARED_L2:
        assert _TOOL_AUTHORITY.get(tool_id) is AuthorityTier.L2_REVERSIBLE, (
            f"{tool_id!r} is forward-declared as L2 but the mapping says "
            f"{_TOOL_AUTHORITY.get(tool_id)}"
        )


def test_forward_declared_l3_tools_present_in_mapping() -> None:
    for tool_id in _FORWARD_DECLARED_L3:
        assert _TOOL_AUTHORITY.get(tool_id) is AuthorityTier.L3_IRREVERSIBLE, (
            f"{tool_id!r} is forward-declared as L3 but the mapping says "
            f"{_TOOL_AUTHORITY.get(tool_id)}"
        )


def test_unknown_tools_require_approval() -> None:
    """``infer_authority`` must default to L1 so an unmapped tool fails
    closed (safer to ask for confirmation than to silently run)."""

    assert infer_authority(["nonexistent_tool_xyz"]) is AuthorityTier.L3_IRREVERSIBLE


def test_infer_authority_picks_highest_tier() -> None:
    assert infer_authority(["file_reader_tool"]) is AuthorityTier.L1_READONLY
    assert infer_authority(["preview_tool"]) is AuthorityTier.L1_READONLY
    assert infer_authority(["deploy_tool"]) is AuthorityTier.L3_IRREVERSIBLE
    # Mixed inputs collapse to the highest tier present.
    assert (
        infer_authority(["file_reader_tool", "preview_tool"])
        is AuthorityTier.L1_READONLY
    )
    assert (
        infer_authority(["file_reader_tool", "deploy_tool"])
        is AuthorityTier.L3_IRREVERSIBLE
    )
