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
METRICS_PATH = ROOT / "repair-metrics.json"
PATCH_TEST_OUTPUT = ROOT / "pytest-patch-output.txt"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
MAX_REPAIR_ROUNDS = 3
PATCH_RETRIES = 2
MODEL_TIMEOUT = 420
PROTECTED_PARTS = {"tests", "test", "scripts", ".github"}


def fail(message):
    print(f"Patch proposal rejected: {message}", file=sys.stderr)
    raise SystemExit(1)


def run_git(*args, input_text=None):
    return subprocess.run(["git", *args], cwd=ROOT, text=True, input=input_text, capture_output=True)


def load_context():
    if not CONTEXT_PATH.exists():
        fail("failure-context.json is missing")
    try:
        return json.loads(CONTEXT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"could not read failure context: {error}")


def run_pytest_with_report():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--cov=.", "--cov-context=test",
         "--cov-report=", "--json-report", "--json-report-file=pytest-report.json"],
        cwd=ROOT, text=True, capture_output=True,
    )
    PATCH_TEST_OUTPUT.write_text(result.stdout + result.stderr, encoding="utf-8")
    return result


def allowed_files_from_context(context):
    allowed = set()
    for failure in context.get("failed_tests", []):
        for item in failure.get("candidate_source_files", []):
            name = item.get("path", "")
            path = Path(name)
            if (path.suffix == ".py" and not path.is_absolute() and ".." not in path.parts
                    and not any(part in PROTECTED_PARTS for part in path.parts)):
                allowed.add(path.as_posix())
    return allowed


def read_exact_source(path):
    target = (ROOT / path).resolve()
    target.relative_to(ROOT)
    return target.read_text(encoding="utf-8")


def build_prompt(context, allowed, feedback=None):
    sources = {}
    for failure in context.get("failed_tests", []):
        for item in failure.get("candidate_source_files", []):
            path = item.get("path")
            source = item.get("source")
            if path in allowed and isinstance(source, str):
                sources[path] = source[:12000]

    failures = [{
        "test": str(failure.get("test", "unknown test")),
        "failure": str(failure.get("failure", "See pytest output."))[:1200],
    } for failure in context.get("failed_tests", [])]

    prompt = f"""You are given the exact current source for a Python file.
Your task is to produce a valid unified diff patch that fixes the failing tests.

STRICT RULES:
- Output only a unified diff patch.
- Do not output markdown fences, code fences, prose, explanations, or commentary.
- Do not invent code or surrounding context.
- Preserve existing function signatures unless absolutely required.
- Use exact source-code context.
- Use the correct file path in diff headers.
- Each hunk header must be valid and match the file content exactly.
- Do not add or remove imports unless necessary.
- Keep the change minimal.
- If a safe patch is not clear, return only: NO_PATCH

ALLOWED_FILES: {json.dumps(sorted(allowed))}
FAILURES: {json.dumps(failures, ensure_ascii=False)}
APPLICATION_SOURCE: {json.dumps(sources, ensure_ascii=False)}
"""
    if feedback:
        prompt += f"\nYour previous patch was rejected: {feedback}\nReturn a corrected unified diff only.\n"
    return prompt


def extract_diff(raw_text):
    text = str(raw_text).strip()
    if not text or text == "NO_PATCH":
        return None
    text = re.sub(r"^```(?:diff|patch|text)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("--- ")
    if start < 0:
        return None
    diff = text[start:]
    if re.search(r"^\+\+\+ ", diff, re.MULTILINE) and "@@" in diff:
        return diff
    return None


def files_in_diff(diff):
    files = set()
    for line in diff.splitlines():
        if line.startswith("--- ") or line.startswith("+++ "):
            name = line[4:].split("\t", 1)[0].strip()
            if name != "/dev/null":
                if name.startswith(("a/", "b/")):
                    name = name[2:]
                files.add(name)
    return files


def validate_and_apply(diff, allowed):
    files = files_in_diff(diff)
    if not files:
        raise ValueError("patch has no file headers")
    if not files.issubset(allowed):
        raise ValueError(f"patch references non-allowlisted paths: {sorted(files - allowed)}")
    for file_name in files:
        target = (ROOT / file_name).resolve()
        try:
            target.relative_to(ROOT)
        except ValueError:
            raise ValueError(f"patch path escapes repository: {file_name}")
        if not target.is_file() or target.suffix != ".py":
            raise ValueError(f"patch target is not an existing Python source file: {file_name}")

    git_apply = run_git("apply", "--check", "-", input_text=diff)
    if git_apply.returncode != 0:
        raise ValueError(f"git apply --check rejected patch: {git_apply.stderr.strip() or git_apply.stdout.strip()}")
    apply_result = run_git("apply", "-", input_text=diff)
    if apply_result.returncode != 0:
        raise ValueError(f"git apply failed to apply patch: {apply_result.stderr.strip() or apply_result.stdout.strip()}")

    changed = run_git("diff", "--name-only")
    changed_paths = {line.strip() for line in changed.stdout.splitlines() if line.strip()}
    if not changed_paths or not changed_paths.issubset(allowed):
        raise ValueError(f"working tree changes exceed allowlist: {sorted(changed_paths - allowed)}")
    return sorted(changed_paths)


def write_metrics(payload):
    METRICS_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def request_and_apply(context, allowed, attempt):
    feedback = None
    last_error = "model returned no unified diff"
    for retry in range(1, PATCH_RETRIES + 1):
        body = json.dumps({
            "model": MODEL,
            "prompt": build_prompt(context, allowed, feedback),
            "stream": False,
            "options": {"temperature": 0.0, "num_ctx": 8192, "num_predict": 2048},
        }).encode("utf-8")
        request = Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=MODEL_TIMEOUT) as response:
                result = json.loads(response.read().decode("utf-8"))
            raw = result.get("response", "")
            diff = extract_diff(raw)
            PATCH_PATH.write_text(diff or str(raw), encoding="utf-8")
            if not diff:
                raise ValueError(f"model output was not a unified diff: {str(raw)[:500]}")
            changed_files = validate_and_apply(diff, allowed)
            return changed_files
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, AttributeError, ValueError) as error:
            last_error = str(error)
            feedback = last_error
            print(f"Patch generation retry {retry}/{PATCH_RETRIES} rejected: {last_error}", file=sys.stderr)
            write_metrics({"model": MODEL, "attempt": attempt, "retry": retry,
                           "status": "patch_rejected", "error": last_error,
                           "failed_patch_saved": PATCH_PATH.exists()})
    fail(f"model failed to produce an applicable patch after {PATCH_RETRIES} tries: {last_error}")


def rebuild_context():
    result = subprocess.run([sys.executable, "scripts/build_failure_context.py"], cwd=ROOT,
                            capture_output=True, text=True)
    if result.returncode:
        fail(f"could not rebuild failure context: {result.stderr.strip()}")
    context = load_context()
    if not context.get("failed_tests"):
        fail("no failing tests were found in the latest pytest report")
    return context


def repair_loop():
    context = load_context()
    for attempt in range(1, MAX_REPAIR_ROUNDS + 1):
        allowed = allowed_files_from_context(context)
        if not allowed:
            fail("no eligible application Python files were selected")
        print(f"Repair attempt {attempt}: {len(context.get('failed_tests', []))} failures; model={MODEL}.")
        changed_files = request_and_apply(context, allowed, attempt)
        result = run_pytest_with_report()
        if result.returncode == 0:
            write_metrics({"model": MODEL, "attempt": attempt, "status": "repair_passed",
                           "changed_files": changed_files})
            print(f"Full test suite passed after repair attempt {attempt}.")
            output = os.environ.get("GITHUB_OUTPUT")
            if output:
                with open(output, "a", encoding="utf-8") as handle:
                    handle.write("applied=true\n")
            return
        write_metrics({"model": MODEL, "attempt": attempt, "status": "tests_failed",
                       "changed_files": changed_files, "pytest_exit_code": result.returncode})
        context = rebuild_context()
    fail(f"repair attempts exhausted after {MAX_REPAIR_ROUNDS} rounds")


if __name__ == "__main__":
    repair_loop()
