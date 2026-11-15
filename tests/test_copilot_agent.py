import json
import sys
from pathlib import Path

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
