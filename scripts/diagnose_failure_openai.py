import json
import os
from pathlib import Path

from openai import OpenAI


MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def main():
    repo = os.environ.get("GITHUB_REPOSITORY", "demo/repo")
    sha = os.environ.get("GITHUB_SHA", "local")
    output_file = Path("pytest-output.txt")

    if not output_file.exists():
        print("No pytest output file found. Nothing to diagnose.")
        return

    log_text = output_file.read_text(encoding="utf-8")[-12000:]
    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        print("OPENAI_API_KEY is not set. Skipping OpenAI diagnosis.")
        return

    client = OpenAI(api_key=api_key)
    prompt = f"""
You are a senior software engineer.
Repository: {repo}
Commit: {sha}

Diagnose this failing Python test output. Return strictly valid JSON with keys:
root_cause, suggested_fix, confidence, files_to_review

Test output:
{log_text}
"""

    response = client.responses.create(
        model=MODEL,
        input=[
            {"role": "system", "content": "Return only valid JSON."},
            {"role": "user", "content": prompt},
        ],
    )

    diagnosis_text = response.output_text.strip()
    diagnosis = json.loads(diagnosis_text)
    print(json.dumps(diagnosis, indent=2))
    Path("ai-diagnosis-openai.json").write_text(
        json.dumps(diagnosis, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
