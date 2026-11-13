# Self-Healing CI Demo

This portfolio experiment shows an AI-assisted test-failure diagnosis workflow using a local Llama model through [Ollama](https://ollama.com/). It runs in GitHub Actions and does not require an OpenAI API key or paid model API. GitHub Actions runner time and bandwidth are still subject to your GitHub plan's limits.

## What it does

1. GitHub Actions runs the Python tests.
2. If a test fails, the workflow starts Ollama and downloads `llama3.2:1b`.
3. The failure log is sent to the local Ollama server on that runner.
4. The model's diagnosis is printed and saved as `ai-diagnosis.json`.
5. The workflow ends as failed because the original test failed; it does not change code, open a PR, or merge anything.

## Run the demo

1. Open the **Actions** tab and select **Self-healing CI**.
2. Select **Run workflow** on the `main` branch.
3. Open the run logs. The test should fail on the intentional double-tax bug, then the Ollama diagnosis step should run.

No API key or repository secret is needed for this Ollama setup. The first run downloads the model (about 1.3 GB), which may take a few minutes. GitHub-hosted runner resources and usage limits apply.

## Run tests locally

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
```

The tests are intentionally expected to fail until the double-tax bug in `app.py` is fixed. To try the diagnosis locally, install Ollama and download the same model:

```bash
ollama pull llama3.2:1b
ollama serve
```

In another terminal, run the tests and save their output, then run `python scripts/diagnose_failure.py` with `pytest-output.txt` present.

## Architecture

```text
GitHub Actions runner
  ├─ pytest ── failure log
  ├─ Ollama + llama3.2:1b (local to that runner)
  └─ diagnosis output (human-reviewed; no automatic code changes)
```

## Safety and limitations

- The model only receives the test output; this starter does not send source files or secrets.
- The model's answer is a suggestion, not a verified repair.
- The workflow does not modify repository files, create PRs, or auto-merge.
- The small model may produce incomplete or incorrect diagnoses; review its output.
- This uses a GitHub-hosted runner to run a local model. It avoids per-token API charges, but consumes runner time and downloads the model on runs that need diagnosis.

## Next upgrades

- Add evaluation cases and track diagnosis quality.
- Require human review before any proposed patch is opened as a PR.
- Add strict patch validation and rerun tests before proposing changes.
