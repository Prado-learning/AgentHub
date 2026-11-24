"""Regression coverage for the runnable Harness: effects, persistence, tools and isolation."""

import base64
import io
import json
import subprocess
import sys
import time
import zipfile
from dataclasses import replace
from pathlib import Path
from threading import Event, Thread
import pytest
from fastapi.testclient import TestClient
from app.api.main import app
from app.api.services import (
    execution_service,
    run_store,
    artifact_service,
    conversation_service,
    diff_service,
    attachment_service,
)
from agenthub.adapters.base import AgentResult
from agenthub.adapters.openai_chat.adapter import OpenAIChatAdapter
from agenthub.adapters.openai_chat.client import OpenAICompatibleProvider
from agenthub.domain.run import RunContext
from agenthub.domain.plan import Plan, PlanStep
from agenthub.gateway.gateway import CachingGateway, GatewayDispatch
from agenthub.gateway.cache import InMemoryCache
from agenthub.harness.runner import HarnessRunner
from agenthub.harness.control import (
    RunControl,
    RunCancelled,
    execution_scope,
    check_cancelled,
)
from agenthub.harness.limits import RunLimits
from agenthub.policies import RunPolicy
from agenthub.infrastructure.persistence.json_store import JsonStore, transaction
from agenthub.infrastructure.config.paths import conversation_workspace


class Adapter:
    id = "orchestrator"

    def __init__(self, fn=None):
        self.calls = 0
        self.fn = fn

    def run(self, task, context):
        self.calls += 1
        return (
            self.fn(task, context)
            if self.fn
            else AgentResult(
                agent_id=self.id,
                messages=[{"content": "done", "role": "agent", "sender": self.id}],
            )
        )


def ctx():
    return RunContext(
        conversation_id="conv_demo",
        message="hello",
        history=[],
        selected_agents=["orchestrator"],
        workspace_dir=str(conversation_workspace("conv_demo")),
    )


def plan(*steps):
    return Plan(steps=list(steps), reason="regression")


def step(id="s", **kw):
    return PlanStep(id=id, agent_id="orchestrator", task="task", **kw)


def test_hello_does_not_invoke_profile_tools():
    result = HarnessRunner().run(replace(ctx(), mode="single"))
    assert result.status == "success"
    assert not any(e.type == "tool.started" for e in result.events)


def test_tool_failure_marks_step_failed_and_blocks_dependents(monkeypatch):
    runner = HarnessRunner()
    runner.tool_executor.registry.register(
        "code_review_tool",
        lambda **kw: (_ for _ in ()).throw(ValueError("broken review")),
    )
    result = runner.run(
        ctx(),
        plan=plan(
            replace(
                step(tools=["code_review_tool"], kind="tool"), agent_id="code_reviewer"
            ),
            step("child", depends_on=["s"]),
        ),
    )
    assert result.checkpoint["step_results"]["s"]["status"] == "failed"
    assert "broken review" in result.checkpoint["step_results"]["s"]["error"]
    assert result.checkpoint["step_results"]["child"]["status"] == "skipped"


def test_parallel_batch_honors_step_cap():
    adapter = Adapter()
    runner = HarnessRunner(
        adapters={adapter.id: adapter},
        limits=RunLimits(run_policy=RunPolicy(max_steps=2)),
    )
    result = runner.run(ctx(), plan=plan(*[step(str(i)) for i in range(6)]))
    assert adapter.calls == 2
    assert (
        sum(
            s["status"] == "skipped" for s in result.checkpoint["step_results"].values()
        )
        == 4
    )


def test_upstream_source_survives_review_only_middle_step():
    seen = []

    def run(task, context):
        seen.append(context.upstream_artifacts)
        return AgentResult(
            agent_id="orchestrator",
            artifacts=[
                {
                    "id": "code",
                    "type": "code",
                    "title": "main.py",
                    "content": "EXACT_SOURCE",
                }
            ]
            if len(seen) == 1
            else [],
        )

    runner = HarnessRunner(adapters={"orchestrator": Adapter(run)})
    runner.run(
        ctx(),
        plan=plan(step("a"), step("b", depends_on=["a"]), step("c", depends_on=["b"])),
    )
    assert seen[2][0]["content"] == "EXACT_SOURCE"


def test_cancellation_stops_dependent_effect():
    control = RunControl()

    def run(task, context):
        control.cancelled.set()
        return AgentResult(agent_id="orchestrator")

    runner = HarnessRunner(adapters={"orchestrator": Adapter(run)}, control=control)
    result = runner.run(
        ctx(),
        plan=plan(
            step(), step("effect", tools=["deploy_tool"], kind="tool", depends_on=["s"])
        ),
    )
    assert result.status == "cancelled"
    assert not any(e.type == "tool.started" for e in result.events)


@pytest.mark.parametrize(
    "field", ["conversation", "history", "workspace", "skills", "model", "credentials"]
)
def test_cache_identity_includes_full_context(field):
    from agenthub.adapters.base import AgentTask

    adapter = Adapter()
    adapter.provider = OpenAICompatibleProvider(
        model="real", api_key="key", base_url="http://example.invalid"
    )
    adapter.skills = []
    gateway = CachingGateway(cache=InMemoryCache())
    request = GatewayDispatch(
        endpoint="e",
        task=AgentTask(agent_id="orchestrator", instruction="same"),
        context=ctx(),
        cache_ttl_seconds=60,
    )
    gateway.dispatch(adapter, request)
    gateway.dispatch(adapter, request)
    assert adapter.calls == 1
    if field == "conversation":
        request = replace(request, context=replace(ctx(), conversation_id="other"))
    if field == "history":
        request = replace(
            request, context=replace(ctx(), history=[{"content": "different"}])
        )
    if field == "workspace":
        request = replace(request, context=replace(ctx(), workspace_dir="different"))
    if field == "skills":
        adapter.skills = ["new skill"]
    if field == "model":
        adapter.provider.model = "other"
    if field == "credentials":
        adapter.provider.api_key = "other"
    gateway.dispatch(adapter, request)
    assert adapter.calls == 2


def test_zero_ttl_really_disables_cache():
    from agenthub.adapters.base import AgentTask

    adapter = Adapter()
    gateway = CachingGateway(cache=InMemoryCache())
    request = GatewayDispatch(
        endpoint="e",
        task=AgentTask(agent_id="orchestrator", instruction="same"),
        context=ctx(),
        cache_ttl_seconds=0,
    )
    gateway.dispatch(adapter, request)
    gateway.dispatch(adapter, request)
    assert adapter.calls == 2


def test_native_model_tool_loop_reports_real_attempts_and_usage(monkeypatch):
    import agenthub.adapters.openai_chat.client as client_module

    requests = []
    responses = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call1",
                    "type": "function",
                    "function": {
                        "name": "code_review_tool",
                        "arguments": json.dumps({"code": "eval(user_input)"}),
                    },
                }
            ],
        },
        {
            "role": "assistant",
            "content": "The static review found eval; avoid untrusted input.",
        },
    ]

    def urlopen(request, **kw):
        requests.append(json.loads(request.data))
        return io.BytesIO(
            json.dumps(
                {
                    "choices": [{"message": responses.pop(0)}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 4},
                }
            ).encode()
        )

    monkeypatch.setattr(client_module.request, "urlopen", urlopen)
    adapter = OpenAIChatAdapter(
        "code_reviewer",
        model="fixture",
        api_key="test",
        base_url="http://example.invalid/v1",
    )
    result = HarnessRunner(adapters={"code_reviewer": adapter}).run(
        ctx(),
        plan=plan(replace(step(tools=["code_review_tool"]), agent_id="code_reviewer")),
    )
    assert result.status == "success", result.checkpoint["step_results"]["s"]["error"]
    assert len(requests) == 2 and requests[0]["tools"]
    assert requests[1]["messages"][-1]["role"] == "tool"
    assert "Dynamic eval" in requests[1]["messages"][-1]["content"]
    metrics = next(e.payload for e in result.events if e.type == "run.metrics")
    assert (
        metrics["llm_calls"] == 2
        and metrics["prompt_tokens"] == 20
        and metrics["completion_tokens"] == 8
    )
    assert sum(e.type == "tool.completed" for e in result.events) == 1


def test_model_loop_is_bounded(monkeypatch):
    from agenthub.runtime.agent_runtime import tool_session

    provider = OpenAICompatibleProvider(model="fixture")
    count = []

    def response(*args):
        count.append(1)
        return {
            "role": "assistant",
            "tool_calls": [
                {"id": str(len(count)), "function": {"name": "noop", "arguments": "{}"}}
            ],
        }

    monkeypatch.setattr(provider, "_request_message", response)
    with (
        tool_session([{"type": "function"}], lambda *args: {}),
        pytest.raises(RuntimeError, match="round limit"),
    ):
        provider.complete("task")
    assert len(count) == 9


def test_real_model_without_configuration_is_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="requires"):
        OpenAICompatibleProvider(model="real").complete("hello")


@pytest.mark.parametrize(
    "url",
    [
        "/deployments/..%5C../README.md",
        "/deployments/dep_x/..%5C../README.md",
        "/deployments/dep_x/C:%5CWindows%5Cwin.ini",
    ],
)
def test_windows_path_traversal_is_rejected(url):
    assert TestClient(app).get(url).status_code == 404


def test_untrusted_browser_origin_cannot_mutate():
    assert (
        TestClient(app)
        .post(
            "/conversations", json={}, headers={"Origin": "https://untrusted.invalid"}
        )
        .status_code
        == 403
    )


def make_diff(content):
    artifact_service.ARTIFACTS.write(
        [
            {
                "id": "patch",
                "conversation_id": "conv_demo",
                "type": "diff",
                "content": content,
            }
        ]
    )
    return diff_service.get_structured_diff("patch")


def test_new_file_patch_and_rollback():
    review = make_diff(
        "--- /dev/null\n+++ b/src/new.py\n@@ -0,0 +1 @@\n+print('new')\n"
    )
    result = diff_service.apply_diff_artifact(
        "patch", review_token=review["review_token"], hunk_ids=["0:0"]
    )
    target = conversation_workspace("conv_demo") / "src/new.py"
    assert target.read_text() == "print('new')\n"
    diff_service.rollback_diff_application(result["id"])
    assert not target.exists()


def test_stale_review_and_stale_rollback_refuse_overwrite():
    root = conversation_workspace("conv_demo")
    root.mkdir(parents=True)
    target = root / "a.txt"
    target.write_text("old\n")
    review = make_diff("--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-old\n+new\n")
    target.write_text("changed\n")
    with pytest.raises(ValueError, match="changed"):
        diff_service.apply_diff_artifact("patch", review_token=review["review_token"])
    target.write_text("old\n")
    applied = diff_service.apply_diff_artifact(
        "patch", review_token=review["review_token"]
    )
    target.write_text("user edit\n")
    with pytest.raises(ValueError, match="overwrite"):
        diff_service.rollback_diff_application(applied["id"])
    assert target.read_text() == "user edit\n"


def test_delete_patch_removes_file_and_restores_bytes():
    root = conversation_workspace("conv_demo")
    root.mkdir(parents=True)
    target = root / "a.txt"
    target.write_bytes(b"old\r\n")
    review = make_diff("--- a/a.txt\n+++ /dev/null\n@@ -1 +0,0 @@\n-old\n")
    applied = diff_service.apply_diff_artifact(
        "patch", review_token=review["review_token"]
    )
    assert not target.exists()
    diff_service.rollback_diff_application(applied["id"])
    assert target.read_bytes() == b"old\r\n"


def test_only_selected_hunks_are_applied():
    root = conversation_workspace("conv_demo")
    root.mkdir(parents=True)
    target = root / "a.txt"
    target.write_text("one\ntwo\nthree\n")
    review = make_diff(
        "--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-one\n+ONE\n@@ -3 +3 @@\n-three\n+THREE\n"
    )
    diff_service.apply_diff_artifact(
        "patch", review_token=review["review_token"], hunk_ids=["0:1"]
    )
    assert target.read_text() == "one\ntwo\nTHREE\n"


def test_transaction_rolls_back_all_namespaces(tmp_path):
    a = JsonStore(tmp_path / "a.json")
    b = JsonStore(tmp_path / "b.json")
    with pytest.raises(ValueError), transaction(a, b):
        a.write([1])
        b.write([2])
        raise ValueError("rollback")
    assert a.read() == [] and b.read() == []


def test_sqlite_updates_across_processes(tmp_path):
    script = tmp_path / "append.py"
    script.write_text(
        "from pathlib import Path\nimport sys\nfrom agenthub.infrastructure.persistence.json_store import JsonStore\ns=JsonStore(Path(sys.argv[1]))\nfor i in range(20): s.update(lambda rows:[*rows,i])\n"
    )
    processes = [
        subprocess.Popen(
            [sys.executable, str(script), str(tmp_path / "multi.json")],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(3)
    ]
    for proc in processes:
        _, err = proc.communicate(timeout=20)
        assert proc.returncode == 0, err
    assert len(JsonStore(tmp_path / "multi.json").read()) == 60


def test_docx_and_pptx_extract_text(tmp_path):
    for suffix, name in [
        (".docx", "word/document.xml"),
        (".pptx", "ppt/slides/slide1.xml"),
    ]:
        path = tmp_path / ("doc" + suffix)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(name, "<r><t>Actual document text</t></r>")
        assert (
            attachment_service._extract_text(path, "application/octet-stream")
            == "Actual document text"
        )


def test_restart_marks_inflight_run_interrupted():
    run_store.update_run(
        "interrupted",
        {"status": "running", "checkpoint": {"inflight_steps": ["effect"]}},
    )
    execution_service.recover_interrupted_runs()
    assert run_store.load_run_result("interrupted")["status"] == "interrupted"


def test_async_chat_returns_id_and_persisted_response():
    with TestClient(app) as client:
        request = {
            "conversation_id": "conv_demo",
            "message": {"role": "user", "content": "hello"},
            "selected_agents": ["orchestrator"],
            "agent_mode": "single",
        }
        started = client.post("/chat/start", json=request)
        assert started.status_code == 202, started.text
        run = started.json()["run_id"]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = client.get(f"/runs/{run}").json()
            if state.get("response"):
                break
            time.sleep(0.02)
        assert state["status"] == "success", state
        assert state["response"]["run_id"] == run
        assert state["events"] and state["cursor"] == len(state["events"])


def test_publication_and_messages_commit_atomically(monkeypatch):
    conversation_service.get_conversation("conv_demo")
    result = execution_service.execute_context(ctx(), plan=plan(step()))
    original = run_store.update_run

    def fail_publication(run_id, updates):
        if "publication" in updates:
            raise RuntimeError("disk failure")
        return original(run_id, updates)

    monkeypatch.setattr(run_store, "update_run", fail_publication)
    with pytest.raises(RuntimeError, match="disk failure"):
        execution_service.publish_result(result)
    assert conversation_service.list_messages("conv_demo") == []
    assert artifact_service.list_artifacts("conv_demo") == []
    monkeypatch.setattr(run_store, "update_run", original)
    first = execution_service.publish_result(result)
    second = execution_service.publish_result(result)
    assert first["messages"] and second["messages"] == []
    assert len(conversation_service.list_messages("conv_demo")) == len(
        first["messages"]
    )


def test_provider_credentials_do_not_cross_provider_boundaries(monkeypatch):
    from agenthub.infrastructure.config.models import resolve_model_selection

    monkeypatch.setenv("OPENAI_API_KEY", "generic-secret")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://generic.invalid/v1")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://deepseek.invalid/v1")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    selected = resolve_model_selection("deepseek")
    assert selected.api_key == ""


def test_empty_data_dir_uses_workspace_default(monkeypatch):
    from agenthub.infrastructure.config.paths import data_root, PROJECT_ROOT

    monkeypatch.setenv("AGENTHUB_DATA_DIR", "")
    assert data_root() == PROJECT_ROOT / "agent-workspace"


def test_restart_finishes_unpublished_results_without_reexecuting():
    conversation_service.get_conversation("conv_demo")
    result = execution_service.execute_context(ctx(), plan=plan(step()))
    assert not conversation_service.list_messages("conv_demo")
    execution_service.recover_interrupted_runs()
    snapshot = run_store.load_run_result(result.run_id)
    assert snapshot["response"]["status"] == "success"
    count = len(conversation_service.list_messages("conv_demo"))
    execution_service.recover_interrupted_runs()
    assert len(conversation_service.list_messages("conv_demo")) == count


def test_workflow_tool_nodes_use_harness_and_approval():
    from app.api.services.workflow_service import run_workflow_artifact
    from app.api.services import decision_service
    from agenthub.tools.builtin import deploy

    conversation_service.get_conversation("conv_demo")
    workflow = {
        "nodes": [
            {"id": "input", "type": "input"},
            {
                "id": "deploy",
                "type": "tool",
                "tool_id": "deploy_tool",
                "arguments": {"preview_html": "<p>approved workflow</p>"},
                "depends_on": ["input"],
            },
        ]
    }
    saved = artifact_service.save_artifacts(
        "conv_demo",
        "fixture",
        [{"id": "workflow", "type": "workflow", "content": json.dumps(workflow)}],
    )[0]
    result = run_workflow_artifact(saved["id"])
    assert result["status"] == "waiting_approval"
    assert not deploy.DEPLOYMENT_DIR.exists()
    decision = decision_service.list_pending_confirmations()[0]
    decision_service.confirm_step(
        run_id=result["run_id"], step_id="deploy", fingerprint=decision["fingerprint"]
    )
    resumed = execution_service.resume_run(result["run_id"])
    assert resumed["status"] == "success"
    assert any(a["type"] == "deployment" for a in resumed["artifacts"])


def test_resume_preserves_model_call_budget():
    from agenthub.domain.authority import AuthorityTier

    runner = HarnessRunner(control=RunControl(max_llm_calls=1))
    runner.control.llm_calls = 1
    result = runner.run(ctx(), plan=plan(step(authority=AuthorityTier.L2_REVERSIBLE)))
    resumed = HarnessRunner(control=RunControl(max_llm_calls=1))
    resumed.run(ctx(), checkpoint=result.checkpoint)
    assert resumed.control.llm_calls == 1
    from agenthub.harness.control import BudgetExceeded

    with pytest.raises(BudgetExceeded):
        resumed.control.model_call()


def test_single_agent_deploy_intent_requires_approval():
    result = HarnessRunner().run(
        replace(ctx(), mode="single", message="deploy this page")
    )
    assert result.status == "waiting_approval"
    assert not any(e.type == "tool.started" for e in result.events)


def test_new_chat_passes_saved_source_to_tools(monkeypatch):
    from app.api.services.chat_service import build_chat_response
    from agenthub.tools.builtin import deploy

    conversation_service.get_conversation("conv_demo")
    artifact_service.save_artifacts(
        "conv_demo",
        "previous",
        [
            {
                "id": "source",
                "type": "code",
                "language": "html",
                "content": "<h1>PREVIOUS_SOURCE</h1>",
            }
        ],
    )
    result = build_chat_response(
        {
            "conversation_id": "conv_demo",
            "message": {
                "role": "user",
                "content": "@deploy_tool deploy the previous source",
            },
            "selected_agents": ["orchestrator"],
            "agent_mode": "single",
        }
    )
    from app.api.services import decision_service

    pending = decision_service.list_pending_confirmations()[0]
    assert result["status"] == "waiting_approval"
    assert "PREVIOUS_SOURCE" in json.dumps(pending["arguments"])
    assert not deploy.DEPLOYMENT_DIR.exists()


@pytest.mark.parametrize("with_child", [False, True])
def test_cli_cancellation_terminates_the_managed_process(
    tmp_path, monkeypatch, with_child
):
    import threading
    from agenthub.adapters.process_adapter import run_cli_agent
    from agenthub.adapters.base import AgentTask

    script = tmp_path / "slow_cli.py"
    child_code = (
        "from pathlib import Path\nimport time\nPath('started').write_text('yes')\n"
        "time.sleep(1)\nPath('finished').write_text('unexpected')\ntime.sleep(60)\n"
    )
    script.write_text(
        (
            "import subprocess, sys, time\nfrom pathlib import Path\n"
            f"subprocess.Popen([sys.executable, '-c', {child_code!r}])\n"
            "time.sleep(1)\nPath('parent_finished').write_text('unexpected')\ntime.sleep(60)\n"
        )
        if with_child
        else child_code
    )
    monkeypatch.setenv("TEST_CLI_COMMAND", f'"{sys.executable}" "{script}"')
    workspace = tmp_path / "project"
    control = RunControl(timeout_seconds=8)

    def cancel_when_started():
        deadline = time.monotonic() + 5
        while not (workspace / "started").exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        control.cancelled.set()

    canceller = threading.Thread(target=cancel_when_started)
    canceller.start()
    started_at = time.monotonic()
    try:
        with execution_scope(control), pytest.raises(RunCancelled):
            run_cli_agent(
                agent_id="test",
                name="Test",
                task=AgentTask(agent_id="test", instruction="wait"),
                context=replace(ctx(), workspace_dir=str(workspace)),
                env_command_key="TEST_CLI_COMMAND",
            )
    finally:
        canceller.join(timeout=6)
    assert time.monotonic() - started_at < 5
    assert (workspace / "started").exists()
    # An orphan would write these markers even after the adapter returned.
    time.sleep(1.2)
    assert not (workspace / "finished").exists()
    assert not (workspace / "parent_finished").exists()
