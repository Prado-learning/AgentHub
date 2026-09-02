"""P2 — semantic cache keys.

Two contracts:

* :func:`cache_key` returns a stable sha256 digest of the JSON-encoded
  parts; identical inputs always collide.
* :func:`semantic_key` namespaces the digest, strips noise fields
  (timestamps, request ids) recursively, and preserves the order of
  list elements so ``[a, b]`` and ``[b, a]`` are still distinct.
"""

from __future__ import annotations

import pytest

from agenthub.gateway.cache import cache_key, semantic_key


def test_cache_key_is_stable() -> None:
    a = cache_key(["endpoint", "instruction", 1, 2])
    b = cache_key(["endpoint", "instruction", 1, 2])
    assert a == b


def test_cache_key_changes_with_input() -> None:
    assert cache_key(["endpoint", "v1"]) != cache_key(["endpoint", "v2"])


def test_semantic_key_includes_namespace_prefix() -> None:
    key = semantic_key("chat", ["hello"])
    assert key.startswith("chat:")
    assert len(key) > len("chat:")


def test_semantic_key_strips_top_level_timestamps() -> None:
    a = semantic_key("chat", ["prompt", {"timestamp": "2026-01-01", "text": "hi"}])
    b = semantic_key("chat", ["prompt", {"timestamp": "2026-09-09", "text": "hi"}])
    assert a == b


def test_semantic_key_strips_nested_noise() -> None:
    payload = {
        "request_id": "abc-123",
        "trace_id": "trace-1",
        "messages": [
            {"role": "user", "content": "hi", "timestamp": "2026-01-01"},
        ],
    }
    a = semantic_key("adapter", [payload])
    b = semantic_key("adapter", [
        {
            "messages": [{"role": "user", "content": "hi"}],
        }
    ])
    assert a == b


def test_semantic_key_preserves_distinct_list_orders() -> None:
    a = semantic_key("chat", ["a", "b"])
    b = semantic_key("chat", ["b", "a"])
    assert a != b


def test_semantic_key_namespaces_avoid_collisions() -> None:
    a = semantic_key("adapter_a", ["x"])
    b = semantic_key("adapter_b", ["x"])
    assert a != b


def test_semantic_key_rejects_empty_namespace() -> None:
    with pytest.raises(ValueError):
        semantic_key("", ["x"])
    with pytest.raises(ValueError):
        semantic_key("   ", ["x"])


def test_semantic_key_rejects_out_of_range_length() -> None:
    with pytest.raises(ValueError):
        semantic_key("ns", ["x"], length=4)
    with pytest.raises(ValueError):
        semantic_key("ns", ["x"], length=128)


def test_semantic_key_keeps_non_noisy_field_values() -> None:
    a = semantic_key("chat", [{"user": "alice", "content": "hi"}])
    b = semantic_key("chat", [{"user": "bob", "content": "hi"}])
    assert a != b


def test_semantic_key_length_is_honoured() -> None:
    full = semantic_key("chat", ["x"], length=64)
    short = semantic_key("chat", ["x"], length=16)
    assert full.endswith(full.split(":")[1])
    assert len(full.split(":")[1]) == 64
    assert len(short.split(":")[1]) == 16
