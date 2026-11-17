import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import copilot_agent

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import propose_and_apply_patch


class FakeResponse:
    def __init__(self, value):
        self.payload = json.dumps(value).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


def test_start_task_uses_user_token_and_selected_branch(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout):
        seen["request"] = request
        seen["timeout"] = timeout
        return FakeResponse({"id": "task-123"})

    monkeypatch.setenv("COPILOT_AGENT_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_REF_NAME", "test/repair")
    monkeypatch.setattr(copilot_agent, "urlopen", fake_urlopen)

    assert copilot_agent.start_task("Analyze the failures") == "task-123"
    request = seen["request"]
    assert request.method == "POST"
    assert request.get_header("Authorization").startswith("Bearer ")
    assert request.get_header("Authorization").endswith("test-token")
    assert json.loads(request.data) == {
        "prompt": "Analyze the failures",
        "base_ref": "test/repair",
        "create_pull_request": False,
    }


def test_start_task_explains_missing_user_token(monkeypatch):
    monkeypatch.delenv("COPILOT_AGENT_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

    with pytest.raises(copilot_agent.AgentError, match="user-to-server token"):
        copilot_agent.start_task("Analyze the failures")


def test_wait_for_task_returns_branch_artifact(monkeypatch):
    responses = iter([
        {"state": "in_progress"},
        {"state": "completed", "artifacts": [{
            "type": "branch",
            "data": {"head_ref": "copilot/repair-task"},
        }]},
    ])
    monkeypatch.setenv("COPILOT_AGENT_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setattr(copilot_agent, "_request_json", lambda *_args: next(responses))
    monkeypatch.setattr(copilot_agent.time, "sleep", lambda _seconds: None)

    assert copilot_agent.wait_for_task("task-123") == "copilot/repair-task"


def test_wait_for_task_rejects_unsuccessful_state(monkeypatch):
    monkeypatch.setenv("COPILOT_AGENT_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setattr(
        copilot_agent, "_request_json", lambda *_args: {"state": "failed"}
    )

    with pytest.raises(copilot_agent.AgentError, match="ended in state failed"):
        copilot_agent.wait_for_task("task-123")


def test_task_branch_requires_branch_artifact():
    with pytest.raises(copilot_agent.AgentError, match="without a branch artifact"):
        copilot_agent._task_branch({"state": "completed"})


def test_changed_files_uses_task_branch_fork_point(monkeypatch):
    task_commit = "c" * 40
    latest_base = "d" * 40
    fork_point = "b" * 40
    workflow_commit = "a" * 40
    diff_args = []

    def fake_run(args, **_kwargs):
        if args[1] == "diff":
            diff_args.extend(args)
            return SimpleNamespace(returncode=0, stdout="app.py\n", stderr="")
        if args[1:3] == ["merge-base", "--is-ancestor"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[1] == "merge-base":
            return SimpleNamespace(returncode=0, stdout=fork_point + "\n", stderr="")
        if args[1:3] == ["rev-parse", "--verify"]:
            revision = task_commit if not any(
                item[1] == "fetch" and "refs/heads/main" in item[-1]
                for item in fake_run.calls
            ) else latest_base
            return SimpleNamespace(returncode=0, stdout=revision + "\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    fake_run.calls = []

    def record_run(args, **kwargs):
        fake_run.calls.append(args)
        return fake_run(args, **kwargs)

    monkeypatch.setenv("GITHUB_REF_NAME", "main")
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    monkeypatch.setattr(copilot_agent.subprocess, "run", record_run)

    assert copilot_agent.changed_files_in_task("copilot/repair", workflow_commit) == {
        "app.py"
    }
    assert diff_args[-1] == f"{fork_point}..{task_commit}"


def test_validate_patch_accepts_app_only_unified_diff():
    diff = (
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1,3 +1,3 @@\n"
        "-import math\n"
        "+import math as math\n"
        " \n"
        " \n"
    )

    propose_and_apply_patch.validate_patch(diff)

def test_validate_patch_rejects_changes_outside_app():
    diff = (
        "diff --git a/tests/test_app.py b/tests/test_app.py\n"
        "--- a/tests/test_app.py\n"
        "+++ b/tests/test_app.py\n"
    )

    with pytest.raises(ValueError, match="app.py"):
        propose_and_apply_patch.validate_patch(diff)


def test_validate_patch_rejects_file_mode_changes():
    diff = (
        "diff --git a/app.py b/app.py\n"
        "old mode 100644\n"
        "new mode 100755\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1,3 +1,3 @@\n"
        "-import math\n"
        "+import math as math\n"
        " \n"
        " \n"
    )

    with pytest.raises(ValueError, match="mode changes"):
        propose_and_apply_patch.validate_patch(diff)


@pytest.mark.parametrize(
    "patch",
    [
        "diff --git a/app.py b/app.py\nGIT binary patch\nliteral 5\n",
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n"
        "-import math\n+import math as math\n"
        "diff --git a/tests/test_app.py b/tests/test_app.py\n"
        "GIT binary patch\nliteral 5\n",
    ],
)
def test_validate_patch_rejects_binary_or_multiple_file_sections(patch):
    with pytest.raises(ValueError):
        propose_and_apply_patch.validate_patch(patch)
