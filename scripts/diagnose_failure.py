import json
import os
from pathlib import Path

from openai import OpenAI


def main():
    repo = os.environ.get("GITHUB_REPOSITORY", "demo/repo")
    sha = os.environ.get("GITHUB_SHA", "local")
    output_file = Path("pytest-output.txt")

    if not output_file.exists():
        print("No pytest output file found. Nothing to diagnose.")
        return

    log_text = output_file.read_text(encoding="utf-8")
    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        print("OPENAI_API_KEY is not set. Skipping AI diagnosis.")
        print("--- Pytest failure log ---")
        print(log_text)
        return

    client = OpenAI(api_key=api_key)

    prompt = f"""
You are a senior software engineer working in a repo named {repo}.
The current commit is {sha}.

Your job is to diagnose a failing Python test suite.
Return valid JSON only with the following keys:
- root_cause
- suggested_fix
- confidence
- files_to_review

Here is the failing test output:

{log_text}
"""

    response = client.responses.create(
        model="gpt-4o-mini",
        input=[
            {"role": "system", "content": "You are a precise debugging assistant. Analyze the test failure and provide a concise diagnosis. Return valid JSON only."},
            {"role": "user", "content": prompt},
        ],
    )

    diagnosis = response.output_text.strip()
    print(diagnosis)

    try:
        parsed = json.loads(diagnosis)
        Path("ai-diagnosis.json").write_text(json.dumps(parsed, indent=2), encoding="utf-8")
    except json.JSONDecodeError:
        Path("ai-diagnosis.json").write_text(json.dumps({"raw_response": diagnosis}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
