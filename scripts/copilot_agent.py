"""Helpers for invoking GitHub Copilot's cloud-agent Tasks API."""

import json
import os
import re
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

API_ROOT = "https://api.github.com"
API_VERSION = "2026-03-10"
TERMINAL_STATES = {"completed", "failed", "timed_out", "cancelled"}
TASK_TIMEOUT_SECONDS = 240
POLL_INTERVAL_SECONDS = 5


class AgentError(RuntimeError):
    """Raised when an agent task or its result cannot be used safely."""


def _repository():
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    parts = repository.split("/")
    if len(parts) != 2 or any(
        part in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9_.-]+", part)
        for part in parts
    ):
        raise AgentError("GITHUB_REPOSITORY must contain a valid owner/repository.")
    return parts


def _request_json(url, token, body=None, timeout=30):
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "X-GitHub-Api-Version": API_VERSION,
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:1000]
        raise AgentError(f"GitHub Copilot API returned HTTP {error.code}: {detail}") from error
    except (URLError, TimeoutError, UnicodeError, json.JSONDecodeError) as error:
        raise AgentError(f"GitHub Copilot API request failed: {error}") from error
    if not isinstance(result, dict):
        raise AgentError("GitHub Copilot API returned an invalid response.")
    return result


def _token():
    token = os.environ.get("COPILOT_AGENT_TOKEN", "")
    if not token:
        raise AgentError(
            "COPILOT_AGENT_TOKEN is not set. Configure it as a repository secret "
            "containing a user-to-server token with Agent tasks read/write access."
        )
    return token


def _base_ref():
    ref = os.environ.get("GITHUB_BASE_REF") or os.environ.get("GITHUB_REF_NAME", "")
    if not ref or "\n" in ref or "\r" in ref:
        raise AgentError("Could not determine a valid base branch for the Copilot task.")
    checked = subprocess.run(
        ["git", "check-ref-format", f"refs/heads/{ref}"],
        text=True, capture_output=True,
    )
    if checked.returncode:
        raise AgentError("Could not determine a valid base branch for the Copilot task.")
    return ref


def _base_sha():
    sha = os.environ.get("COPILOT_BASE_SHA") or os.environ.get("GITHUB_SHA", "")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise AgentError("Could not determine the base commit for the Copilot task.")
    return sha


def start_task(prompt):
    owner, repo = _repository()
    url = f"{API_ROOT}/agents/repos/{quote(owner)}/{quote(repo)}/tasks"
    result = _request_json(url, _token(), {
        "prompt": prompt,
        "base_ref": _base_ref(),
        "create_pull_request": False,
    })
    task_id = result.get("id")
    if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", task_id):
        raise AgentError("GitHub Copilot API did not return a valid task ID.")
    print(f"Started GitHub Copilot task {task_id}.")
    return task_id


def _task_branch(task):
    artifacts = task.get("artifacts", [])
    for artifact in artifacts if isinstance(artifacts, list) else []:
        if not isinstance(artifact, dict):
            continue
        if artifact.get("type") == "branch":
            data = artifact.get("data")
            head_ref = data.get("head_ref") if isinstance(data, dict) else None
            if head_ref:
                return head_ref
    sessions = task.get("sessions", [])
    for session in sessions if isinstance(sessions, list) else []:
        if isinstance(session, dict) and session.get("head_ref"):
            return session["head_ref"]
    raise AgentError("Copilot task completed without a branch artifact.")


def wait_for_task(task_id, timeout_seconds=TASK_TIMEOUT_SECONDS):
    owner, repo = _repository()
    url = f"{API_ROOT}/agents/repos/{quote(owner)}/{quote(repo)}/tasks/{quote(task_id)}"
    token = _token()
    deadline = time.monotonic() + timeout_seconds
    while True:
        task = _request_json(url, token)
        state = task.get("state")
        print(f"GitHub Copilot task {task_id}: {state}.")
        if state == "completed":
            return _task_branch(task)
        if state in TERMINAL_STATES:
            raise AgentError(f"GitHub Copilot task {task_id} ended in state {state}.")
        if state not in {"queued", "in_progress", "idle", "waiting_for_user"}:
            raise AgentError(f"GitHub Copilot task returned unknown state: {state!r}.")
        if time.monotonic() >= deadline:
            raise AgentError(f"GitHub Copilot task exceeded the {timeout_seconds}-second limit.")
        time.sleep(min(POLL_INTERVAL_SECONDS, max(0, deadline - time.monotonic())))


def fetch_task_file(branch, path, base_sha):
    if (not isinstance(branch, str) or not re.fullmatch(r"[A-Za-z0-9_./-]+", branch)
            or branch.startswith("-")):
        raise AgentError("Copilot task returned an invalid branch name.")
    if (not isinstance(path, str) or Path(path).is_absolute()
            or not re.fullmatch(r"[A-Za-z0-9_./-]+", path)
            or ".." in Path(path).parts):
        raise AgentError("Requested task file path is invalid.")
    checked = subprocess.run(
        ["git", "check-ref-format", f"refs/heads/{branch}"],
        text=True, capture_output=True,
    )
    if checked.returncode:
        raise AgentError("Copilot task returned an invalid branch name.")
    fetched = subprocess.run(
        ["git", "fetch", "--no-tags", "origin", f"refs/heads/{branch}"],
        text=True, capture_output=True,
    )
    if fetched.returncode:
        raise AgentError(f"Could not fetch Copilot task branch: {fetched.stderr.strip()}")
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base_sha, "FETCH_HEAD"],
        text=True, capture_output=True,
    )
    if ancestry.returncode:
        raise AgentError("Copilot task branch is not based on the workflow commit.")
    result = subprocess.run(
        ["git", "show", f"FETCH_HEAD:{path}"],
        text=True, capture_output=True,
    )
    if result.returncode:
        raise AgentError(f"Copilot task branch is missing {Path(path).name}.")
    return result.stdout


def workflow_base_sha():
    return _base_sha()


def changed_files_in_task(branch, base_sha):
    if not isinstance(branch, str) or not re.fullmatch(r"[A-Za-z0-9_./-]+", branch):
        raise AgentError("Copilot task returned an invalid branch name.")
    checked = subprocess.run(
        ["git", "check-ref-format", f"refs/heads/{branch}"],
        text=True, capture_output=True,
    )
    if checked.returncode:
        raise AgentError("Copilot task returned an invalid branch name.")
    fetched = subprocess.run(
        ["git", "fetch", "--no-tags", "origin", f"refs/heads/{branch}"],
        text=True, capture_output=True,
    )
    if fetched.returncode:
        raise AgentError(f"Could not fetch Copilot task branch: {fetched.stderr.strip()}")
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_sha}...FETCH_HEAD"],
        text=True, capture_output=True,
    )
    if result.returncode:
        raise AgentError(f"Could not inspect Copilot task changes: {result.stderr.strip()}")
    return {line for line in result.stdout.splitlines() if line}
