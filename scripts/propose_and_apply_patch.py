import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path.cwd().resolve()
CONTEXT_PATH = ROOT / "failure-context.json"
PATCH_PATH = ROOT / "ai-proposed.patch"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:1b")


def fail(message):
    print(f"Patch proposal rejected: {message}", file=sys.stderr)
    raise SystemExit(1)


def run_git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)


def extract_json_object(raw_text):
    text = raw_text.strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def parse_model_patch_payload(response_data):
    if isinstance(response_data, dict):
        payload = response_data
    else:
        payload = extract_json_object(str(response_data))

    if payload is None:
        return None

    for key in ("edits", "replacements", "changes", "patches"):
        if key in payload and isinstance(payload[key], list):
            return payload[key]

    if isinstance(payload, dict):
        if {"file", "old", "new"}.issubset(payload.keys()):
            return [payload]
        if {"path", "old", "new"}.issubset(payload.keys()):
            return [payload]
        if {"file", "find", "replace"}.issubset(payload.keys()):
            return [{"file": payload["file"], "old": payload["find"], "new": payload["replace"]}]
        if {"path", "find", "replace"}.issubset(payload.keys()):
            return [{"path": payload["path"], "old": payload["find"], "new": payload["replace"]}]

    return None


def ensure_allowlisted(path_value, allowed):
    path = Path(path_value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"non-relative path: {path_value}")
    if path.as_posix() not in allowed:
        raise ValueError(f"non-allowlisted file: {path_value}")
    if any(part in {"tests", "test", "scripts", ".github"} for part in path.parts):
        raise ValueError(f"protected path: {path_value}")
    return path


def write_patch_from_diff(path_value, original_text, updated_text):
    diff = subprocess.run(
        ["git", "diff", "--no-index", "--no-ext-diff", "--binary", "--", "/dev/null", str(ROOT / path_value)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if diff.returncode not in {0, 1}:
        raise RuntimeError(f"unable to generate patch for {path_value}: {diff.stderr.strip()}")

    file_patch = diff.stdout
    if not file_patch.strip():
        raise RuntimeError(f"empty diff generated for {path_value}")
    return file_patch


def main():
    if not CONTEXT_PATH.exists():
        fail("failure-context.json is missing")
    context = json.loads(CONTEXT_PATH.read_text(encoding="utf-8"))
    allowed = set()
    for failure in context.get("failed_tests", []):
        for item in failure.get("candidate_source_files", []):
            name = item.get("path", "")
            path = Path(name)
            if (path.suffix == ".py" and not path.is_absolute()
                    and ".." not in path.parts
                    and not any(part in {"tests", "test", "scripts"} for part in path.parts)):
                allowed.add(path.as_posix())
    if not allowed:
        fail("no eligible application source files were selected")

    prompt = f"""Repair the failing Python tests using the smallest possible change.
Choose only existing application Python files from ALLOWED_FILES. Do not edit tests, scripts, CI files, docs, or dependencies.
Return JSON only. Use a structured object with one of these keys:
- "edits" = list of objects like {"file": "path/to/file.py", "old": "exact old snippet", "new": "exact replacement snippet"}
- or "replacements" = same layout
Use the exact text from the source file. Do not wrap the response in markdown fences.
If there is no safe code fix, return {"edits": []}.

ALLOWED_FILES: {json.dumps(sorted(allowed))}

Failure context:
{json.dumps(context, ensure_ascii=False)}
"""
    payload = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0},
    }).encode("utf-8")
    request = Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=300) as response:
            result = json.loads(response.read().decode("utf-8"))
        response_text = result.get("response", "")
        response_data = extract_json_object(response_text)
        if response_data is None:
            fail("model returned invalid JSON")
        edits = parse_model_patch_payload(response_data)
        if edits is None:
            fail("model did not return a valid edit list")
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, AttributeError) as error:
        fail(f"could not obtain a valid model response: {error}")

    if not edits:
        fail("model returned no safe edit list")

    applied_files = set()
    for entry in edits:
        file_key = entry.get("file") or entry.get("path")
        old_text = entry.get("old") or entry.get("find")
        new_text = entry.get("new") or entry.get("replace")
        if not isinstance(file_key, str) or not isinstance(old_text, str) or not isinstance(new_text, str):
            fail("edit entries are missing file, old, or new values")

        target = ensure_allowlisted(file_key, allowed)
        source_file = ROOT / target
        current = source_file.read_text(encoding="utf-8")
        if old_text not in current:
            fail(f"exact old text not found in {file_key}")
        updated = current.replace(old_text, new_text)
        if updated == current:
            fail(f"replacement had no effect for {file_key}")
        source_file.write_text(updated, encoding="utf-8")
        applied_files.add(target.as_posix())

    diff_output = run_git("diff", "--no-ext-diff", "--binary")
    if diff_output.returncode != 0:
        fail(f"git diff failed: {diff_output.stderr.strip()}")

    patch_text = diff_output.stdout.rstrip() + "\n"
    if not patch_text.strip():
        fail("generated patch is empty")

    PATCH_PATH.write_text(patch_text, encoding="utf-8")
    print(f"Applied proposed patch to: {', '.join(sorted(applied_files))}")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write("applied=true\n")


if __name__ == "__main__":
    main()
