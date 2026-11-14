import ast
import json
import re
from pathlib import Path


ROOT = Path.cwd().resolve()
REPORT_PATH = ROOT / "pytest-report.json"
COVERAGE_PATH = ROOT / ".coverage"
OUTPUT_PATH = ROOT / "failure-context.json"
MAX_CONTEXT_CHARS = 10000
MAX_FILE_CHARS = 2500
MAX_FAILED_TESTS = 3
EXCLUDED_PARTS = {".git", ".venv", "venv", "site-packages", "__pycache__"}


def repo_file(path):
    try:
        resolved = path.resolve()
        resolved.relative_to(ROOT)
    except (OSError, ValueError):
        return None
    if not resolved.is_file() or resolved.suffix != ".py":
        return None
    if any(part in EXCLUDED_PARTS for part in resolved.parts):
        return None
    return resolved


def test_path_from_nodeid(nodeid):
    return repo_file(ROOT / nodeid.split("::", 1)[0])


def imported_project_files(test_file):
    found = set()
    try:
        tree = ast.parse(test_file.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return found
    module_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            module_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            module_names.add(node.module)
    for module_name in module_names:
        relative = Path(*module_name.split("."))
        for candidate in (ROOT / relative.with_suffix(".py"), ROOT / relative / "__init__.py"):
            local = repo_file(candidate)
            if local:
                found.add(local)
    return found


def coverage_candidates(nodeid):
    found = {}
    try:
        from coverage import CoverageData
        data = CoverageData(basename=str(COVERAGE_PATH))
        data.read()
        for raw_path in data.measured_files():
            path = repo_file(Path(raw_path))
            if not path or "tests" in path.relative_to(ROOT).parts:
                continue
            by_line = data.contexts_by_lineno(str(raw_path))
            executed = [line for line, contexts in by_line.items()
                        if any(ctx == nodeid or ctx.startswith(nodeid + "|") for ctx in contexts)]
            if executed:
                found[path] = sorted(executed)
    except Exception as error:
        print(f"Coverage context lookup unavailable: {error}")
    return found


def source_entry(path, executed_lines=None):
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if len(text) > MAX_FILE_CHARS:
        text = text[:MAX_FILE_CHARS] + "\n... [source truncated to reduce model prompt size]"
    entry = {"path": path.relative_to(ROOT).as_posix(), "source": text}
    if executed_lines:
        entry["executed_lines_for_failed_test"] = executed_lines[:80]
    return entry


def failure_text(failure):
    call = failure.get("call") or {}
    crash = call.get("crash") or {}
    message = crash.get("message") or failure.get("longrepr") or "See pytest output."
    return str(message)[:800]


def group_key_for_failure(failure):
    """Approximate a root-cause group from the test's target function name."""
    nodeid = str(failure.get("nodeid", "unknown test"))
    name = nodeid.split("::")[-1].split("[", 1)[0]
    if not name.startswith("test_"):
        return name
    name = name[5:]
    # Remove common assertion/behavior descriptions so tests for the same
    # function (e.g. calculate_total) are grouped together.
    name = re.split(r"_(?:applies|rejects|strips|lowercases|uses|returns|formats|raises|handles)_", name, maxsplit=1)[0]
    return name or "unknown"


def main():
    if not REPORT_PATH.exists():
        raise SystemExit("pytest-report.json is missing; run pytest with --json-report first.")
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    all_failures = [test for test in report.get("tests", []) if test.get("outcome") == "failed"]
    failures = all_failures[:MAX_FAILED_TESTS]
    results = []
    budget = MAX_CONTEXT_CHARS
    for failure in failures:
        nodeid = failure.get("nodeid", "unknown test")
        test_file = test_path_from_nodeid(nodeid)
        candidates = coverage_candidates(nodeid) if test_file else {}
        if not candidates and test_file:
            candidates = {path: [] for path in imported_project_files(test_file)}
        files = []
        if test_file:
            entry = source_entry(test_file)
            if entry:
                files.append(entry)
        for path, lines in sorted(candidates.items(), key=lambda item: str(item[0])):
            entry = source_entry(path, lines)
            if entry and all(old["path"] != entry["path"] for old in files):
                files.append(entry)
        compact_files = []
        for entry in files:
            serialized = json.dumps(entry, ensure_ascii=False)
            if len(serialized) > budget:
                remain = max(0, budget - 200)
                if remain <= 0:
                    break
                entry["source"] = entry["source"][:remain] + "\n... [context truncated]"
                serialized = json.dumps(entry, ensure_ascii=False)
            budget -= len(serialized)
            compact_files.append(entry)
            if budget <= 0:
                break
        results.append({
            "test": nodeid,
            "failure": failure_text(failure),
            "candidate_source_files": compact_files,
            "group_id": group_key_for_failure(failure),
        })
        if budget <= 0:
            break

    groups = {}
    for item in results:
        groups.setdefault(item["group_id"], []).append(item["test"])
    payload = {
        "failed_tests": results,
        "failure_groups": [
            {"group_id": group_id, "tests": tests}
            for group_id, tests in sorted(groups.items())
        ],
        "failure_batch": {
            "limit": MAX_FAILED_TESTS,
            "selected": len(results),
            "total": len(all_failures),
            "remaining": max(0, len(all_failures) - len(results)),
        },
        "context_note": "At most three failures are included per repair round. Source and failure details are truncated to bound prompt size. Groups are heuristic buckets based on test-name target/function; they are not confirmed root causes.",
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Built compact source context for {len(results)} of {len(all_failures)} failed test(s) (limit {MAX_FAILED_TESTS}).")
    for failure in results:
        print(f"- [{failure['group_id']}] {failure['test']}: " + ", ".join(item["path"] for item in failure["candidate_source_files"]))


if __name__ == "__main__":
    main()
