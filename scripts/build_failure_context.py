import ast
import json
from pathlib import Path


ROOT = Path.cwd().resolve()
REPORT_PATH = ROOT / "pytest-report.json"
COVERAGE_PATH = ROOT / ".coverage"
OUTPUT_PATH = ROOT / "failure-context.json"
PYTEST_OUTPUT_PATHS = (ROOT / "pytest-patch-output.txt", ROOT / "pytest-output.txt")
MAX_CONTEXT_CHARS = 30000
MAX_FILE_CHARS = 8000
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
    """Best-effort fallback when per-test coverage has no matching context."""
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
            executed = []
            for line, contexts in by_line.items():
                if any(context == nodeid or context.startswith(nodeid + "|") for context in contexts):
                    executed.append(line)
            if executed:
                found[path] = sorted(executed)
    except Exception as error:
        # Coverage issues should fall back to imports, not hide diagnosis.
        print(f"Coverage context lookup unavailable: {error}")
    return found


def source_entry(path, executed_lines=None):
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if len(text) > MAX_FILE_CHARS:
        text = text[:MAX_FILE_CHARS] + "\n... [file truncated]"
    entry = {"path": path.relative_to(ROOT).as_posix(), "source": text}
    if executed_lines:
        entry["executed_lines_for_failed_test"] = executed_lines[:200]
    return entry


def failure_message(item):
    call = item.get("call") or {}
    crash = call.get("crash") or {}
    message = crash.get("message")
    if message:
        return str(message)
    longrepr = item.get("longrepr")
    if longrepr:
        return str(longrepr)[:4000]
    return "See pytest-output.txt or pytest-patch-output.txt for details."


def collect_failures(report):
    failures = [item for item in report.get("tests", []) if item.get("outcome") == "failed"]
    # Collection errors can make pytest exit nonzero without any test outcome=failed.
    for collector in report.get("collectors", []):
        if collector.get("outcome") == "failed":
            failures.append({
                "nodeid": collector.get("nodeid", "pytest collection"),
                "outcome": "failed",
                "longrepr": collector.get("longrepr", "Test collection failed."),
            })
    return failures


def pytest_diagnostic():
    for path in PYTEST_OUTPUT_PATHS:
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if text:
            return text[-8000:]
    return "Pytest exited nonzero, but its JSON report contained no failed test or collection entries."


def main():
    if not REPORT_PATH.exists():
        raise SystemExit("pytest-report.json is missing; run pytest with --json-report first.")

    try:
        report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Could not read pytest JSON report: {error}")

    all_failures = collect_failures(report)
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
            test_entry = source_entry(test_file)
            if test_entry:
                files.append(test_entry)
        for path, lines in sorted(candidates.items(), key=lambda item: str(item[0])):
            entry = source_entry(path, lines)
            if entry and all(existing["path"] != entry["path"] for existing in files):
                files.append(entry)

        encoded_files = []
        for entry in files:
            serialized = json.dumps(entry, ensure_ascii=False)
            if len(serialized) > budget:
                remaining = max(0, budget - 300)
                if remaining <= 0:
                    break
                entry["source"] = entry["source"][:remaining] + "\n... [context truncated]"
                serialized = json.dumps(entry, ensure_ascii=False)
            budget -= len(serialized)
            encoded_files.append(entry)
            if budget <= 0:
                break

        results.append({
            "test": nodeid,
            "failure": failure_message(failure),
            "candidate_source_files": encoded_files,
        })
        if budget <= 0:
            break

    payload = {
        "failed_tests": results,
        "failure_batch": {
            "limit": MAX_FAILED_TESTS,
            "selected": len(results),
            "total": len(all_failures),
            "remaining": max(0, len(all_failures) - len(results)),
        },
        "report_summary": report.get("summary", {}),
        "context_note": "All selected failures are sent together in one repair request. Coverage identifies files executed by each failed test; it does not prove which line caused the failure.",
    }
    if not results:
        payload["diagnostic"] = pytest_diagnostic()
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"Built source context for {len(results)} of {len(all_failures)} failed test(s) "
        f"(maximum {MAX_FAILED_TESTS} per repair round): {OUTPUT_PATH}"
    )
    for failure in results:
        print(f"- {failure['test']}: " + ", ".join(file["path"] for file in failure["candidate_source_files"]))
    if len(all_failures) > len(results):
        print(f"- {len(all_failures) - len(results)} failed test(s) remain for later repair rounds.")
    if not results:
        print("- No failed tests were present in the JSON report; included pytest diagnostics instead.")


if __name__ == "__main__":
    main()
